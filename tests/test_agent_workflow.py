"""LangGraph path tests with deterministic agent decisions and local tools."""

from collections.abc import Sequence
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from app.agents.models import (
    AgentDecision,
    AgentDecisionType,
    AgentTerminationReason,
    AgentToolRequest,
)
from app.core.exceptions import AssessmentGenerationError
from app.graph.workflow import AgenticAssessmentWorkflow, build_assessment_graph
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.tools.models import (
    GetKnowledgeDocumentArguments,
    ObservedKnowledgeDocument,
    SearchKnowledgeArguments,
    ToolExecutionResult,
)
from app.tools.registry import ToolDefinition, ToolRegistry
from tests.factories import build_assessment_result


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual compliance review is slow",
        desired_outcome="Reduce preparation time with human approval",
    )


def _evidence() -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic governance policy",
        content="Human review is required for high-impact recommendations.",
        similarity_score=0.94,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )


class ScriptedAgent:
    """One fake agent whose decisions make graph routing deterministic."""

    def __init__(self, decisions: Sequence[AgentDecision]) -> None:
        self.decisions = list(decisions)
        self.decision_calls: list[dict[str, Any]] = []
        self.synthesis_calls: list[dict[str, Any]] = []

    def decide(self, **kwargs: Any) -> AgentDecision:
        self.decision_calls.append(kwargs)
        return self.decisions.pop(0)

    def synthesize(self, **kwargs: Any) -> AssessmentResult:
        self.synthesis_calls.append(kwargs)
        return build_assessment_result()


def _tool_decision(name: str, arguments: dict[str, object]) -> AgentDecision:
    return AgentDecision(
        action=AgentDecisionType.TOOL,
        tool_request=AgentToolRequest(name=name, arguments=arguments),
    )


def _workflow(
    agent: ScriptedAgent,
    registry: ToolRegistry,
    *,
    max_steps: int = 5,
    max_tool_calls: int = 5,
) -> AgenticAssessmentWorkflow:
    return AgenticAssessmentWorkflow(
        agent=agent,
        tools=registry,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        recursion_limit=25,
    )


def test_graph_compiles_with_explicit_reason_tool_synthesis_nodes() -> None:
    agent = ScriptedAgent([AgentDecision(action=AgentDecisionType.SYNTHESIZE)])

    compiled = build_assessment_graph(agent=agent, tools=ToolRegistry([]))

    assert {"reason", "execute_tool", "synthesize", "fail"} <= set(compiled.nodes)


def test_path_a_synthesizes_without_tool_use() -> None:
    agent = ScriptedAgent([AgentDecision(action=AgentDecisionType.SYNTHESIZE)])

    outcome = _workflow(agent, ToolRegistry([])).run(assessment_id=str(uuid4()), request=_request())

    assert outcome.execution.steps_used == 1
    assert outcome.execution.tools_used == []
    assert outcome.execution.termination_reason == AgentTerminationReason.AGENT_STOPPED
    assert len(agent.decision_calls) == 1
    assert len(agent.synthesis_calls) == 1


def test_path_b_searches_once_then_synthesizes_with_observed_evidence() -> None:
    evidence = _evidence()
    handler = Mock(
        return_value=ToolExecutionResult(
            tool_name="search_knowledge",
            success=True,
            summary="Knowledge search returned 1 relevant chunk(s).",
            evidence=(evidence,),
        )
    )
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="search_knowledge",
                description="Search knowledge.",
                arguments_model=SearchKnowledgeArguments,
                handler=handler,
            )
        ]
    )
    agent = ScriptedAgent(
        [
            _tool_decision("search_knowledge", {"query": "governance", "top_k": 2}),
            AgentDecision(action=AgentDecisionType.SYNTHESIZE),
        ]
    )

    outcome = _workflow(agent, registry).run(assessment_id=str(uuid4()), request=_request())

    assert outcome.evidence == (evidence,)
    assert outcome.execution.tools_used == ["search_knowledge"]
    assert agent.decision_calls[1]["evidence"] == [evidence]
    assert agent.synthesis_calls[0]["evidence"] == [evidence]
    handler.assert_called_once()


def test_path_c_supports_two_allowed_read_only_tools_before_synthesis() -> None:
    evidence = _evidence()
    document = ObservedKnowledgeDocument(
        document_id=evidence.document_id,
        title=evidence.document_title,
        source_type=evidence.source_type,
        content_excerpt="Expanded synthetic context.",
        metadata={"synthetic": True},
        truncated=False,
    )

    def search_handler(_: BaseModel) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name="search_knowledge",
            success=True,
            summary="Knowledge search returned 1 relevant chunk(s).",
            evidence=(evidence,),
        )

    def document_handler(_: BaseModel) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name="get_knowledge_document",
            success=True,
            summary="Knowledge document was retrieved.",
            document=document,
        )

    registry = ToolRegistry(
        [
            ToolDefinition(
                "search_knowledge",
                "Search knowledge.",
                SearchKnowledgeArguments,
                search_handler,
            ),
            ToolDefinition(
                "get_knowledge_document",
                "Read document.",
                GetKnowledgeDocumentArguments,
                document_handler,
            ),
        ]
    )
    agent = ScriptedAgent(
        [
            _tool_decision("search_knowledge", {"query": "governance", "top_k": 2}),
            _tool_decision("get_knowledge_document", {"document_id": str(evidence.document_id)}),
            AgentDecision(action=AgentDecisionType.SYNTHESIZE),
        ]
    )

    outcome = _workflow(agent, registry).run(assessment_id=str(uuid4()), request=_request())

    assert outcome.execution.steps_used == 3
    assert outcome.execution.tools_used == ["search_knowledge", "get_knowledge_document"]
    assert agent.synthesis_calls[0]["documents"] == [document]


def test_path_d_max_steps_terminates_and_duplicate_call_is_cached() -> None:
    handler = Mock(
        return_value=ToolExecutionResult(
            tool_name="search_knowledge",
            success=True,
            summary="Knowledge search returned 0 relevant chunk(s).",
        )
    )
    registry = ToolRegistry(
        [
            ToolDefinition(
                "search_knowledge",
                "Search knowledge.",
                SearchKnowledgeArguments,
                handler,
            )
        ]
    )
    duplicate = {"query": "sensitive internal query", "top_k": 1}
    agent = ScriptedAgent(
        [
            _tool_decision("search_knowledge", duplicate),
            _tool_decision("search_knowledge", duplicate),
        ]
    )

    outcome = _workflow(agent, registry, max_steps=2).run(
        assessment_id=str(uuid4()), request=_request()
    )

    assert outcome.execution.termination_reason == AgentTerminationReason.MAX_STEPS_REACHED
    assert outcome.execution.steps_used == 2
    assert handler.call_count == 1
    assert "sensitive internal query" not in outcome.execution.model_dump_json()
    tool_events = [event for event in outcome.execution.trace if event.tool_status is not None]
    assert [event.tool_status for event in tool_events] == ["completed", "cached"]


def test_max_tool_calls_forces_synthesis_before_another_agent_decision() -> None:
    handler = Mock(
        return_value=ToolExecutionResult(
            tool_name="search_knowledge",
            success=True,
            summary="Knowledge search returned 0 relevant chunk(s).",
        )
    )
    registry = ToolRegistry(
        [
            ToolDefinition(
                "search_knowledge",
                "Search knowledge.",
                SearchKnowledgeArguments,
                handler,
            )
        ]
    )
    agent = ScriptedAgent([_tool_decision("search_knowledge", {"query": "governance", "top_k": 1})])

    outcome = _workflow(agent, registry, max_tool_calls=1).run(
        assessment_id=str(uuid4()), request=_request()
    )

    assert outcome.execution.termination_reason == AgentTerminationReason.MAX_TOOL_CALLS_REACHED
    assert len(agent.decision_calls) == 1
    assert len(agent.synthesis_calls) == 1


def test_path_e_tool_failure_is_observed_then_workflow_recovers() -> None:
    def failing_handler(_: BaseModel) -> ToolExecutionResult:
        raise RuntimeError("private database detail")

    registry = ToolRegistry(
        [
            ToolDefinition(
                "search_knowledge",
                "Search knowledge.",
                SearchKnowledgeArguments,
                failing_handler,
            )
        ]
    )
    agent = ScriptedAgent(
        [
            _tool_decision("search_knowledge", {"query": "governance", "top_k": 1}),
            AgentDecision(action=AgentDecisionType.SYNTHESIZE),
        ]
    )

    outcome = _workflow(agent, registry).run(assessment_id=str(uuid4()), request=_request())

    assert outcome.result == build_assessment_result()
    assert any(event.event_type == "tool_failed" for event in outcome.execution.trace)
    assert "private database detail" not in outcome.execution.model_dump_json()


def test_explicit_fail_decision_terminates_without_synthesis() -> None:
    agent = ScriptedAgent([AgentDecision(action=AgentDecisionType.FAIL)])

    with pytest.raises(AssessmentGenerationError):
        _workflow(agent, ToolRegistry([])).run(assessment_id=str(uuid4()), request=_request())

    assert agent.synthesis_calls == []
