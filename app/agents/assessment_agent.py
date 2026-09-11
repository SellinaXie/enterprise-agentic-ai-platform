"""One OpenAI-backed reasoning agent for V4 assessment orchestration."""

import json
from collections.abc import Callable
from time import perf_counter, sleep
from typing import Any, Protocol

from openai import OpenAI, OpenAIError

from app.agents.models import AgentDecision, AgentDecisionType, AgentToolRequest
from app.agents.prompts import (
    AGENT_SYSTEM_INSTRUCTIONS,
    build_agent_reasoning_input,
    build_agent_synthesis_context,
)
from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    OpenAIClientNotConfiguredError,
)
from app.models.knowledge import RetrievedEvidence
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.runtime.resilience import run_with_retry
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.services.assessment_prompt import build_assessment_prompt
from app.services.assessments import AssessmentGenerator
from app.tools.models import ObservedKnowledgeDocument, ToolHistoryEntry


class AssessmentAgent(Protocol):
    """Provider-independent operations required by the LangGraph nodes."""

    def decide(
        self,
        *,
        request: AssessmentRequest,
        evidence: list[RetrievedEvidence],
        documents: list[ObservedKnowledgeDocument],
        tool_history: list[ToolHistoryEntry],
        step: int,
        max_steps: int,
        tool_schemas: list[dict[str, Any]],
    ) -> AgentDecision: ...

    def synthesize(
        self,
        *,
        request: AssessmentRequest,
        evidence: list[RetrievedEvidence],
        documents: list[ObservedKnowledgeDocument],
    ) -> AssessmentResult: ...


class OpenAIAssessmentAgent:
    """Use strict OpenAI function calls for decisions and V3 generation for synthesis."""

    def __init__(
        self,
        *,
        model: str,
        generator: AssessmentGenerator,
        store_responses: bool = False,
        client_provider: Callable[[], OpenAI],
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._model = model
        self._generator = generator
        self._store_responses = store_responses
        self._client_provider = client_provider
        self._retry_policy = retry_policy
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics
        self._sleeper = sleeper

    def decide(
        self,
        *,
        request: AssessmentRequest,
        evidence: list[RetrievedEvidence],
        documents: list[ObservedKnowledgeDocument],
        tool_history: list[ToolHistoryEntry],
        step: int,
        max_steps: int,
        tool_schemas: list[dict[str, Any]],
    ) -> AgentDecision:
        """Request zero or one strict function call without retaining provider state."""
        decision_input = build_agent_reasoning_input(
            request=request,
            evidence=evidence,
            documents=documents,
            tool_history=tool_history,
            step=step,
            max_steps=max_steps,
        )
        try:

            def request_provider() -> Any:
                started = perf_counter()
                response = None
                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "input": [
                        {"role": "system", "content": AGENT_SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": decision_input},
                    ],
                    "tools": tool_schemas,
                    "tool_choice": "auto",
                    "parallel_tool_calls": False,
                    "max_output_tokens": 200,
                    "store": self._store_responses,
                }
                if self._timeout_seconds is not None:
                    kwargs["timeout"] = self._timeout_seconds
                try:
                    response = self._client_provider().responses.create(**kwargs)
                    return response
                finally:
                    if self._metrics is not None:
                        self._metrics.record_model_call(
                            max(0, round((perf_counter() - started) * 1_000)), response
                        )

            response = (
                run_with_retry(
                    request_provider,
                    policy=self._retry_policy,
                    sleeper=self._sleeper,
                    on_retry=(self._metrics.record_retry if self._metrics is not None else None),
                )
                if self._retry_policy is not None
                else request_provider()
            )
        except OpenAIClientNotConfiguredError:
            raise
        except OpenAIError as exc:
            raise LLMProviderError from exc
        except (TypeError, ValueError) as exc:
            raise InvalidLLMResponseError from exc

        function_calls = [
            item for item in response.output if getattr(item, "type", None) == "function_call"
        ]
        if not function_calls:
            return AgentDecision(action=AgentDecisionType.SYNTHESIZE)

        tool_call = function_calls[0]
        try:
            parsed_arguments = json.loads(tool_call.arguments)
        except (json.JSONDecodeError, TypeError):
            parsed_arguments = {}
        if not isinstance(parsed_arguments, dict):
            parsed_arguments = {}

        return AgentDecision(
            action=AgentDecisionType.TOOL,
            tool_request=AgentToolRequest(
                name=str(tool_call.name),
                arguments=parsed_arguments,
            ),
        )

    def synthesize(
        self,
        *,
        request: AssessmentRequest,
        evidence: list[RetrievedEvidence],
        documents: list[ObservedKnowledgeDocument],
    ) -> AssessmentResult:
        """Reuse the existing V3 schema-constrained generator for the final output."""
        context = build_agent_synthesis_context(evidence, documents)
        return self._generator.generate(build_assessment_prompt(request, context))
