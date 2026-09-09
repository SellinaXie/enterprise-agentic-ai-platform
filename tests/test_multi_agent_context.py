"""Context isolation and structured OpenAI boundary tests for V5 agents."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

from openai import OpenAI

from app.agents.architecture_agent import OpenAIArchitectureAgent
from app.agents.architecture_prompt import build_architecture_input
from app.agents.evidence_agent import OpenAIEvidenceAgent
from app.agents.multi_agent_models import EvidenceBrief, EvidenceItem
from app.agents.risk_governance_agent import OpenAIRiskGovernanceAgent
from app.agents.risk_governance_prompt import build_risk_governance_input
from app.agents.structured_output import OpenAIStructuredOutput
from app.agents.synthesis_agent import OpenAISynthesisAgent
from app.agents.synthesis_prompt import build_synthesis_input
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.schemas.assessment import AssessmentRequest
from app.tools.models import SearchKnowledgeArguments, ToolExecutionResult
from app.tools.permissions import AgentToolPermissions
from app.tools.registry import ToolDefinition, ToolRegistry
from tests.factories import (
    build_architecture_recommendation,
    build_assessment_result,
    build_evidence_brief,
    build_risk_governance_review,
)


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Context Isolation Bank",
        industry="Banking",
        business_problem="Manual review is slow",
        desired_outcome="Faster preparation with human approval",
    )


def test_specialist_prompt_builders_receive_only_their_typed_handoffs() -> None:
    request = _request()
    brief = build_evidence_brief()
    architecture = build_architecture_recommendation()
    risk = build_risk_governance_review()

    architecture_input = build_architecture_input(request, brief)
    risk_input = build_risk_governance_input(request, brief)
    synthesis_input = build_synthesis_input(
        request=request,
        evidence_brief=brief,
        architecture=architecture,
        risk_governance=risk,
        degradation_reasons=[],
    )

    assert "evidence_brief" in architecture_input
    assert "risk_governance_review" not in architecture_input
    assert "tool_history" not in architecture_input
    assert "evidence_brief" in risk_input
    assert "architecture_recommendation" not in risk_input
    assert "tool_history" not in risk_input
    assert "architecture_recommendation" in synthesis_input
    assert "risk_governance_review" in synthesis_input
    assert "tool_history" not in synthesis_input
    assert "provider_messages" not in synthesis_input


def test_toolless_specialists_use_schema_parse_without_tool_arguments() -> None:
    client = Mock()
    client.responses.parse.side_effect = [
        SimpleNamespace(output_parsed=build_architecture_recommendation()),
        SimpleNamespace(output_parsed=build_risk_governance_review()),
        SimpleNamespace(output_parsed=build_assessment_result()),
    ]
    structured = OpenAIStructuredOutput(
        model="gpt-4.1-mini",
        store_responses=False,
        retry_limit=0,
        client_provider=lambda: cast(OpenAI, client),
    )
    architecture_agent = OpenAIArchitectureAgent(structured)
    risk_agent = OpenAIRiskGovernanceAgent(structured)
    synthesis_agent = OpenAISynthesisAgent(structured)
    brief = build_evidence_brief()

    architecture = architecture_agent.analyze(_request(), brief)
    risk = risk_agent.review(_request(), brief)
    synthesis_agent.synthesize(
        request=_request(),
        evidence_brief=brief,
        architecture=architecture,
        risk_governance=risk,
        degradation_reasons=[],
    )

    assert client.responses.parse.call_count == 3
    for call in client.responses.parse.call_args_list:
        assert "tools" not in call.kwargs
        assert "tool_choice" not in call.kwargs
        assert len(call.kwargs["input"]) == 2


def test_structured_output_retry_is_bounded() -> None:
    client = Mock()
    client.responses.parse.side_effect = [
        SimpleNamespace(output_parsed=None),
        SimpleNamespace(output_parsed=build_architecture_recommendation()),
    ]
    structured = OpenAIStructuredOutput(
        model="gpt-4.1-mini",
        store_responses=False,
        retry_limit=1,
        client_provider=lambda: cast(OpenAI, client),
    )

    result = structured.generate(
        system="architecture-only",
        user="typed-input",
        output_model=type(build_architecture_recommendation()),
    )

    assert result == build_architecture_recommendation()
    assert client.responses.parse.call_count == 2


def test_evidence_agent_reuses_registry_and_strips_invented_brief_provenance() -> None:
    evidence = RetrievedEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic approval policy",
        content="Authorized staff retain final approval.",
        similarity_score=0.96,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )
    invented_document = uuid4()
    invented_chunk = uuid4()
    raw_brief = EvidenceBrief(
        summary="Approval controls were found.",
        evidence_items=[
            EvidenceItem(
                claim="Human approval is required.",
                supporting_document_ids=[evidence.document_id, invented_document],
                supporting_chunk_ids=[evidence.chunk_id, invented_chunk],
                relevance="Defines the decision boundary.",
            )
        ],
        evidence_gaps=[],
        confidence="high",
        retrieved_document_ids=[evidence.document_id, invented_document],
        retrieved_chunk_ids=[evidence.chunk_id, invented_chunk],
    )
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
                description="Search existing knowledge.",
                arguments_model=SearchKnowledgeArguments,
                handler=handler,
            )
        ]
    )
    client = Mock()
    client.responses.create.side_effect = [
        SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="function_call",
                    name="search_knowledge",
                    arguments='{"query":"human review","top_k":2}',
                )
            ]
        ),
        SimpleNamespace(output=[SimpleNamespace(type="message")]),
    ]
    client.responses.parse.return_value = SimpleNamespace(output_parsed=raw_brief)
    agent = OpenAIEvidenceAgent(
        model="gpt-4.1-mini",
        tools=registry,
        permissions=AgentToolPermissions(),
        max_steps=4,
        max_tool_calls=4,
        store_responses=False,
        retry_limit=0,
        client_provider=lambda: cast(OpenAI, client),
    )

    result = agent.gather(_request())

    assert result.evidence == (evidence,)
    assert result.brief.retrieved_document_ids == [evidence.document_id]
    assert result.brief.retrieved_chunk_ids == [evidence.chunk_id]
    assert result.brief.evidence_items[0].supporting_document_ids == [evidence.document_id]
    assert result.brief.evidence_items[0].supporting_chunk_ids == [evidence.chunk_id]
    assert result.steps_used == 2
    assert len(result.tool_history) == 1
    handler.assert_called_once()
    first_call = client.responses.create.call_args_list[0]
    assert [schema["name"] for schema in first_call.kwargs["tools"]] == ["search_knowledge"]
    assert first_call.kwargs["parallel_tool_calls"] is False
