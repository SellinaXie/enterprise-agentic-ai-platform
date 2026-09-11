"""Typed framework-agnostic runtime governance and telemetry contracts."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimeModel(BaseModel):
    """Closed base contract for persisted runtime state and API schemas."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RuntimeRiskDecision(StrEnum):
    """Centralized post-validation gate outcomes."""

    AUTO_COMPLETE = "auto_complete"
    COMPLETE_WITH_WARNING = "complete_with_warning"
    REQUIRE_HUMAN_REVIEW = "require_human_review"
    BLOCK_AND_ESCALATE = "block_and_escalate"


class RuntimeRiskLevel(StrEnum):
    """Small policy-neutral risk scale."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RuntimeReasonCode(StrEnum):
    """Machine-readable explanations for non-automatic outcomes."""

    MEDIUM_RISK = "medium_risk"
    HIGH_RISK = "high_risk"
    CRITICAL_RISK = "critical_risk"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    INVALID_PROVENANCE = "invalid_provenance"
    DEGRADED_EXECUTION = "degraded_execution"
    SPECIALIST_UNAVAILABLE = "specialist_unavailable"
    MISSING_HUMAN_OVERSIGHT = "missing_human_oversight"
    MISSING_RISK_MITIGATION = "missing_risk_mitigation"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    MODEL_FAILURE = "model_failure"
    TOOL_FAILURE = "tool_failure"
    RETRIEVAL_FAILURE = "retrieval_failure"
    QUALITY_GATE_FAILED = "quality_gate_failed"


class HumanReviewStatus(StrEnum):
    """Persisted lifecycle of the application-level review boundary."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


class HumanReviewAction(StrEnum):
    """Immutable-style audit event actions."""

    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    REVISION_SUBMITTED = "revision_submitted"


class ExecutionHealth(StrEnum):
    """Public-safe health of an assessment execution."""

    FULL = "full"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    PENDING_HUMAN_REVIEW = "pending_human_review"


class FailureCategory(StrEnum):
    """Stable failure classification without raw exception details."""

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    VALIDATION = "validation"
    POLICY = "policy"
    TIMEOUT = "timeout"
    PROVIDER = "provider"
    RETRIEVAL = "retrieval"
    TOOL = "tool"
    PERSISTENCE = "persistence"
    HUMAN_REJECTION = "human_rejection"


class RuntimeTraceEventType(StrEnum):
    """Safe event vocabulary; events contain no prompts, CoT, or source text."""

    ASSESSMENT_STARTED = "assessment_started"
    RETRIEVAL_STARTED = "retrieval_started"
    RETRIEVAL_COMPLETED = "retrieval_completed"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    RETRY = "retry"
    TIMEOUT = "timeout"
    QUALITY_GATE_EVALUATED = "quality_gate_evaluated"
    HUMAN_REVIEW_REQUESTED = "human_review_requested"
    HUMAN_REVIEW_RESUMED = "human_review_resumed"
    HUMAN_REVIEW_APPROVED = "human_review_approved"
    HUMAN_REVIEW_REJECTED = "human_review_rejected"
    REVISION_REQUESTED = "revision_requested"
    ASSESSMENT_COMPLETED = "assessment_completed"
    ASSESSMENT_FAILED = "assessment_failed"


class RuntimeTraceEvent(RuntimeModel):
    """One compact audit event with only operational metadata."""

    timestamp: datetime
    request_id: str | None = Field(default=None, max_length=128)
    event_type: RuntimeTraceEventType
    component: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=50)
    duration_ms: int | None = Field(default=None, ge=0)
    reason_code: RuntimeReasonCode | None = None


class ProviderTokenUsage(RuntimeModel):
    """Exact provider usage when available; absent counters remain null."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class OperationalTelemetry(RuntimeModel):
    """Structured per-assessment telemetry without sensitive payloads."""

    request_id: str | None = Field(default=None, max_length=128)
    execution_mode: str = Field(min_length=1, max_length=30)
    execution_health: ExecutionHealth
    total_duration_ms: int = Field(ge=0)
    execution_duration_ms: int = Field(ge=0)
    human_wait_duration_ms: int | None = Field(default=None, ge=0)
    retrieval_duration_ms: int | None = Field(default=None, ge=0)
    synthesis_duration_ms: int | None = Field(default=None, ge=0)
    model_call_count: int | None = Field(default=None, ge=0)
    model_call_durations_ms: list[int] = Field(default_factory=list)
    embedding_call_count: int | None = Field(default=None, ge=0)
    tool_call_count: int = Field(ge=0)
    graph_retrieval_used: bool
    vector_retrieval_used: bool
    specialist_durations_ms: dict[str, int | None] = Field(default_factory=dict)
    retry_count: int = Field(default=0, ge=0)
    timeout_count: int = Field(default=0, ge=0)
    degraded_state_count: int = Field(default=0, ge=0)
    human_review_status: HumanReviewStatus
    termination_reason: str = Field(min_length=1, max_length=100)
    token_usage: ProviderTokenUsage | None = None
    estimated_cost: float | None = Field(default=None, ge=0.0)
    estimated_cost_currency: str | None = Field(default=None, max_length=10)
    events: list[RuntimeTraceEvent] = Field(default_factory=list)


class RuntimeRiskPolicy(RuntimeModel):
    """Configurable internal policy; it encodes no external regulatory framework."""

    medium_risk_decision: RuntimeRiskDecision = RuntimeRiskDecision.COMPLETE_WITH_WARNING
    high_risk_decision: RuntimeRiskDecision = RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW
    critical_risk_decision: RuntimeRiskDecision = RuntimeRiskDecision.BLOCK_AND_ESCALATE
    review_on_insufficient_evidence: bool = True
    review_on_degraded_execution: bool = True
    review_on_specialist_unavailable: bool = True
    review_on_tool_failure: bool = True
    block_high_risk_invalid_provenance: bool = True
    block_critical_missing_mitigation: bool = True
    max_human_revisions: int = Field(default=2, ge=0, le=10)


class QualityGateSignals(RuntimeModel):
    """Lightweight structured inputs derived from one generated assessment."""

    risk_level: RuntimeRiskLevel
    evidence_required: bool = False
    evidence_available: bool = False
    provenance_valid: bool = True
    unsupported_claims_detected: bool = False
    degraded_execution: bool = False
    specialist_unavailable: bool = False
    retrieval_failed: bool = False
    tool_failed: bool = False
    model_failed: bool = False
    human_oversight_required: bool = False
    human_oversight_present: bool = True
    mitigations_complete: bool = True


class QualityGateResult(RuntimeModel):
    """Explainable runtime decision and contributing reason codes."""

    decision: RuntimeRiskDecision
    risk_level: RuntimeRiskLevel
    reason_codes: list[RuntimeReasonCode] = Field(default_factory=list)
    review_required: bool
    blocked: bool

    @model_validator(mode="after")
    def validate_decision_flags(self) -> Self:
        if self.review_required != (self.decision == RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW):
            raise ValueError("review_required must match the gate decision")
        if self.blocked != (self.decision == RuntimeRiskDecision.BLOCK_AND_ESCALATE):
            raise ValueError("blocked must match the gate decision")
        return self


class HumanReviewRequest(RuntimeModel):
    """Bounded untrusted reviewer action input."""

    reviewer_id: str | None = Field(default=None, min_length=1, max_length=100)
    comment: str | None = Field(default=None, min_length=1, max_length=2_000)


class HumanReviewRecord(RuntimeModel):
    """Immutable-style persisted audit record."""

    review_id: UUID
    assessment_id: UUID
    action: HumanReviewAction
    previous_status: HumanReviewStatus
    new_status: HumanReviewStatus
    reviewer_id: str | None
    comment: str | None
    reason_codes: list[RuntimeReasonCode]
    revision_number: int = Field(ge=0)
    created_at: datetime


class RuntimeAssessmentState(RuntimeModel):
    """Persisted gate/checkpoint state sufficient to resume finalization."""

    assessment_id: UUID
    gate_result: QualityGateResult
    review_status: HumanReviewStatus
    candidate_result: dict[str, Any] | None = None
    candidate_execution: dict[str, Any] | None = None
    telemetry: OperationalTelemetry
    revision_count: int = Field(ge=0)
    max_revisions: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class RuntimeStatusResponse(RuntimeModel):
    """Safe API status; candidate content remains inside the persistence boundary."""

    assessment_id: UUID
    gate_result: QualityGateResult
    review_status: HumanReviewStatus
    revision_count: int
    max_revisions: int
    telemetry: OperationalTelemetry


class HumanReviewDecision(RuntimeModel):
    """Review transition result returned to API callers."""

    assessment_id: UUID
    action: HumanReviewAction
    review_status: HumanReviewStatus
    assessment_status: str
    revision_count: int


class RetryPolicy(RuntimeModel):
    """Small bounded exponential-backoff policy."""

    max_retries: int = Field(default=2, ge=0, le=10)
    base_delay_ms: int = Field(default=250, ge=0, le=60_000)
    max_delay_ms: int = Field(default=4_000, ge=0, le=60_000)
    jitter_ratio: float = Field(default=0.1, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_delay_bounds(self) -> Self:
        if self.max_delay_ms < self.base_delay_ms:
            raise ValueError("max retry delay must be at least the base delay")
        return self
