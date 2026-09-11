"""Provider-backed reasoning agent for V4 assessment orchestration."""

from collections.abc import Callable
from time import sleep
from typing import Any, Protocol

from app.agents.models import AgentDecision, AgentDecisionType, AgentToolRequest
from app.agents.prompts import (
    AGENT_SYSTEM_INSTRUCTIONS,
    build_agent_reasoning_input,
    build_agent_synthesis_context,
)
from app.models.knowledge import RetrievedEvidence
from app.providers.contracts import StructuredModelProvider
from app.providers.openai import OpenAIStructuredModelProvider
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.services.assessment_prompt import build_assessment_prompt
from app.services.assessments import AssessmentGenerator
from app.services.llm import get_openai_client
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
    """Provider-neutral reasoning agent; name retained for API compatibility."""

    def __init__(
        self,
        *,
        model: str | None = None,
        generator: AssessmentGenerator,
        store_responses: bool = False,
        client_provider: Callable[[], Any] = get_openai_client,
        provider: StructuredModelProvider | None = None,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._generator = generator
        if provider is None:
            if model is None:
                raise ValueError("model is required when provider is not supplied")
            provider = OpenAIStructuredModelProvider(
                model=model,
                store_responses=store_responses,
                client_provider=client_provider,
                retry_policy=retry_policy,
                timeout_seconds=timeout_seconds,
                metrics=metrics,
                sleeper=sleeper,
            )
        self._provider = provider

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
        decision = self._provider.decide_tool_call(
            system=AGENT_SYSTEM_INSTRUCTIONS,
            user=decision_input,
            tools=tool_schemas,
            max_output_tokens=200,
        )
        if decision is None:
            return AgentDecision(action=AgentDecisionType.SYNTHESIZE)

        return AgentDecision(
            action=AgentDecisionType.TOOL,
            tool_request=AgentToolRequest(
                name=decision.name,
                arguments=decision.arguments,
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
