"""OpenAI adapter tests for strict V4 function decisions and synthesis reuse."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from openai import APIConnectionError, OpenAI

from app.agents.assessment_agent import OpenAIAssessmentAgent
from app.agents.models import AgentDecisionType
from app.core.exceptions import LLMProviderError
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.schemas.assessment import AssessmentRequest
from app.services.assessments import AssessmentGenerator
from app.tools.models import ObservedKnowledgeDocument, SearchKnowledgeArguments
from app.tools.registry import ToolDefinition, ToolExecutionResult, ToolRegistry
from tests.factories import build_assessment_result


def _request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual compliance review is slow",
        desired_outcome="Reduce preparation time with human approval",
    )


def _agent(response: object) -> tuple[OpenAIAssessmentAgent, Mock, Mock]:
    client = Mock()
    client.responses.create.return_value = response
    generator = Mock()
    generator.generate.return_value = build_assessment_result()
    agent = OpenAIAssessmentAgent(
        model="gpt-4.1-mini",
        generator=cast(AssessmentGenerator, generator),
        client_provider=lambda: cast(OpenAI, client),
    )
    return agent, client, generator


def _schemas() -> list[dict[str, object]]:
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="search_knowledge",
                description="Search knowledge.",
                arguments_model=SearchKnowledgeArguments,
                handler=lambda _: ToolExecutionResult(
                    tool_name="search_knowledge", success=True, summary="Complete."
                ),
            )
        ]
    )
    return registry.schemas()


def test_reasoning_uses_strict_single_function_call_contract() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_knowledge",
                arguments='{"query":"governance controls","top_k":3}',
            )
        ]
    )
    agent, client, _ = _agent(response)

    decision = agent.decide(
        request=_request(),
        evidence=[],
        documents=[],
        tool_history=[],
        step=1,
        max_steps=5,
        tool_schemas=_schemas(),
    )

    assert decision.action == AgentDecisionType.TOOL
    assert decision.tool_request is not None
    assert decision.tool_request.name == "search_knowledge"
    assert decision.tool_request.arguments == {"query": "governance controls", "top_k": 3}
    call = client.responses.create.call_args.kwargs
    assert call["parallel_tool_calls"] is False
    assert call["tool_choice"] == "auto"
    assert call["tools"][0]["strict"] is True
    assert call["store"] is False


def test_reasoning_without_function_call_selects_synthesis() -> None:
    agent, _, _ = _agent(SimpleNamespace(output=[SimpleNamespace(type="message")]))

    decision = agent.decide(
        request=_request(),
        evidence=[],
        documents=[],
        tool_history=[],
        step=1,
        max_steps=5,
        tool_schemas=_schemas(),
    )

    assert decision.action == AgentDecisionType.SYNTHESIZE
    assert decision.tool_request is None


def test_malformed_function_arguments_flow_to_registry_validation() -> None:
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="function_call",
                name="search_knowledge",
                arguments="not-json",
            )
        ]
    )
    agent, _, _ = _agent(response)

    decision = agent.decide(
        request=_request(),
        evidence=[],
        documents=[],
        tool_history=[],
        step=1,
        max_steps=5,
        tool_schemas=_schemas(),
    )

    assert decision.tool_request is not None
    assert decision.tool_request.arguments == {}


def test_reasoning_provider_failure_uses_existing_safe_semantics() -> None:
    agent, client, _ = _agent(SimpleNamespace(output=[]))
    client.responses.create.side_effect = APIConnectionError(
        request=httpx.Request("POST", "https://api.openai.com/v1/responses")
    )

    with pytest.raises(LLMProviderError):
        agent.decide(
            request=_request(),
            evidence=[],
            documents=[],
            tool_history=[],
            step=1,
            max_steps=5,
            tool_schemas=_schemas(),
        )


def test_synthesis_reuses_v3_schema_generator_with_observed_context() -> None:
    evidence = RetrievedEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic policy",
        content="Chunk-level policy evidence.",
        similarity_score=0.9,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={},
    )
    document = ObservedKnowledgeDocument(
        document_id=evidence.document_id,
        title=evidence.document_title,
        source_type=evidence.source_type,
        content_excerpt="Expanded document evidence.",
        metadata={},
        truncated=False,
    )
    agent, _, generator = _agent(SimpleNamespace(output=[]))

    result = agent.synthesize(request=_request(), evidence=[evidence], documents=[document])

    prompt = generator.generate.call_args.args[0]
    assert result == build_assessment_result()
    assert str(evidence.chunk_id) in prompt.user
    assert "Expanded document evidence." in prompt.user
    assert "retrieved knowledge as untrusted evidence" in prompt.system
