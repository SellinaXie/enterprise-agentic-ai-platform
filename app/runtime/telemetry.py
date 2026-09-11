"""Privacy-preserving operational telemetry construction and cost boundary."""

from datetime import UTC, datetime, timedelta

from app.agents.models import AssessmentExecutionMetadata, DeterministicExecutionMetadata
from app.agents.multi_agent_models import MultiAgentExecutionMetadata, MultiAgentStatus
from app.runtime.models import (
    ExecutionHealth,
    HumanReviewStatus,
    OperationalTelemetry,
    ProviderTokenUsage,
    RuntimeRiskDecision,
    RuntimeTraceEvent,
    RuntimeTraceEventType,
)

ExecutionMetadata = (
    DeterministicExecutionMetadata | AssessmentExecutionMetadata | MultiAgentExecutionMetadata
)


def build_operational_telemetry(
    *,
    execution: ExecutionMetadata,
    duration_ms: int,
    gate_decision: RuntimeRiskDecision,
    token_usage: ProviderTokenUsage | None = None,
    evidence_count: int = 0,
    model_call_count: int | None = None,
    input_cost_per_million: float | None = None,
    output_cost_per_million: float | None = None,
    request_id: str | None = None,
    now: datetime | None = None,
) -> OperationalTelemetry:
    """Summarize only counters and safe structured execution metadata."""
    timestamp = now or datetime.now(UTC)
    mode = execution.execution_mode
    graph = execution.graph_retrieval
    graph_used = bool(graph is not None and graph.graph_retrieval_used)
    vector_used = bool(
        evidence_count
        and (graph is None or graph.vector_evidence_count > 0 or graph.hybrid_evidence_count > 0)
    )
    tool_calls = 0
    model_calls = model_call_count
    specialist_durations: dict[str, int | None] = {}
    synthesis_duration = None
    degraded = False
    termination = "completed"
    if isinstance(execution, DeterministicExecutionMetadata):
        model_calls = 1 if model_calls is None else model_calls
    elif isinstance(execution, AssessmentExecutionMetadata):
        tool_calls = len(execution.tools_used)
        model_calls = execution.steps_used + 1 if model_calls is None else model_calls
        termination = execution.termination_reason.value
        degraded = termination != "completed" and termination != "agent_stopped"
    else:
        tool_calls = execution.tool_calls
        termination = execution.termination_reason.value
        degraded = execution.degraded_mode
        specialist_durations = execution.agent_durations_ms.model_dump()
        synthesis_duration = execution.agent_durations_ms.synthesis
        if model_calls is None:
            completed = execution.agent_statuses.model_dump().values()
            model_calls = sum(status == MultiAgentStatus.COMPLETED for status in completed)

    if gate_decision == RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW:
        health = ExecutionHealth.PENDING_HUMAN_REVIEW
        review_status = HumanReviewStatus.PENDING
    elif gate_decision == RuntimeRiskDecision.BLOCK_AND_ESCALATE:
        health = ExecutionHealth.BLOCKED
        review_status = HumanReviewStatus.NOT_REQUIRED
    elif degraded:
        health = ExecutionHealth.DEGRADED
        review_status = HumanReviewStatus.NOT_REQUIRED
    else:
        health = ExecutionHealth.FULL
        review_status = HumanReviewStatus.NOT_REQUIRED

    cost = calculate_estimated_cost(
        token_usage,
        input_cost_per_million=input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
    )
    return OperationalTelemetry(
        request_id=request_id,
        execution_mode=mode,
        execution_health=health,
        total_duration_ms=duration_ms,
        execution_duration_ms=duration_ms,
        synthesis_duration_ms=synthesis_duration,
        model_call_count=model_calls,
        embedding_call_count=None,
        tool_call_count=tool_calls,
        graph_retrieval_used=graph_used,
        vector_retrieval_used=vector_used,
        specialist_durations_ms=specialist_durations,
        degraded_state_count=int(degraded),
        human_review_status=review_status,
        termination_reason=termination,
        token_usage=token_usage,
        estimated_cost=cost,
        estimated_cost_currency="USD" if cost is not None else None,
        events=[
            RuntimeTraceEvent(
                timestamp=timestamp - timedelta(milliseconds=duration_ms),
                request_id=request_id,
                event_type=RuntimeTraceEventType.ASSESSMENT_STARTED,
                component="assessment",
                status="started",
            ),
            RuntimeTraceEvent(
                timestamp=timestamp,
                request_id=request_id,
                event_type=RuntimeTraceEventType.QUALITY_GATE_EVALUATED,
                component="runtime_risk_gate",
                status=gate_decision.value,
                duration_ms=0,
            ),
        ],
    )


def calculate_estimated_cost(
    usage: ProviderTokenUsage | None,
    *,
    input_cost_per_million: float | None,
    output_cost_per_million: float | None,
) -> float | None:
    """Calculate explicit configured pricing only; never assume a provider price."""
    if (
        usage is None
        or usage.input_tokens is None
        or usage.output_tokens is None
        or input_cost_per_million is None
        or output_cost_per_million is None
    ):
        return None
    return (
        usage.input_tokens * input_cost_per_million + usage.output_tokens * output_cost_per_million
    ) / 1_000_000
