"""No-wait verification that every V7C external boundary receives a timeout."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import httpx
from openai import APIConnectionError, OpenAI

from app.agents.structured_output import OpenAIStructuredOutput
from app.rag.embeddings import OpenAIEmbeddingsService
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.schemas.assessment import AssessmentRequest
from app.services.assessment_prompt import build_assessment_prompt
from app.services.llm import OpenAIAssessmentGenerator
from app.tools.models import SearchKnowledgeArguments, ToolExecutionResult
from app.tools.registry import ToolDefinition, ToolRegistry
from tests.factories import build_architecture_recommendation, build_assessment_result


def test_model_call_receives_explicit_timeout() -> None:
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(output_parsed=build_assessment_result())
    generator = OpenAIAssessmentGenerator(
        model="test-model",
        timeout_seconds=7,
        client_provider=lambda: cast(OpenAI, client),
    )
    request = AssessmentRequest(
        company_name="Synthetic",
        industry="Technology",
        business_problem="A process is slow",
        desired_outcome="Improve it safely",
    )

    generator.generate(build_assessment_prompt(request))

    assert client.responses.parse.call_args.kwargs["timeout"] == 7


def test_model_transient_retry_is_counted() -> None:
    client = Mock()
    client.responses.parse.side_effect = [
        APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/responses")),
        SimpleNamespace(output_parsed=build_assessment_result()),
    ]
    metrics = RuntimeMetricsRecorder()
    generator = OpenAIAssessmentGenerator(
        model="test-model",
        retry_policy=RetryPolicy(max_retries=1, base_delay_ms=0),
        metrics=metrics,
        sleeper=lambda _: None,
        client_provider=lambda: cast(OpenAI, client),
    )
    request = AssessmentRequest(
        company_name="Synthetic",
        industry="Technology",
        business_problem="A process is slow",
        desired_outcome="Improve it safely",
    )

    generator.generate(build_assessment_prompt(request))

    assert client.responses.parse.call_count == 2
    assert metrics.retry_count == 1
    assert len(metrics.model_call_durations_ms) == 2


def test_embedding_call_receives_explicit_timeout() -> None:
    client = Mock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[1.0, 0.0])]
    )
    service = OpenAIEmbeddingsService(
        model="test-embedding",
        dimension=2,
        timeout_seconds=8,
        client_provider=lambda: cast(OpenAI, client),
    )

    service.embed_texts(["synthetic"])

    assert client.embeddings.create.call_args.kwargs["timeout"] == 8


def test_graph_structured_call_receives_explicit_timeout() -> None:
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        output_parsed=build_architecture_recommendation()
    )
    structured = OpenAIStructuredOutput(
        model="test-model",
        store_responses=False,
        retry_limit=0,
        timeout_seconds=9,
        client_provider=lambda: cast(OpenAI, client),
    )

    structured.generate(
        system="graph extraction boundary",
        user="synthetic",
        output_model=type(build_architecture_recommendation()),
    )

    assert client.responses.parse.call_args.kwargs["timeout"] == 9


def test_tool_timeout_is_a_safe_structured_failure() -> None:
    observed: list[float] = []

    def timeout_runner(operation: object, timeout: float) -> ToolExecutionResult:
        del operation
        observed.append(timeout)
        from app.runtime.resilience import OperationTimeoutError

        raise OperationTimeoutError

    registry = ToolRegistry(
        [
            ToolDefinition(
                name="search",
                description="Synthetic read-only search.",
                arguments_model=SearchKnowledgeArguments,
                handler=lambda _: ToolExecutionResult(
                    tool_name="search", success=True, summary="complete"
                ),
            )
        ],
        timeout_seconds=10,
        timeout_runner=timeout_runner,
    )

    result, _, _ = registry.execute("search", {"query": "synthetic", "top_k": 1})

    assert observed == [10]
    assert result.success is False
    assert result.error_code == "tool_timeout"
    assert "exceeded" in result.summary
