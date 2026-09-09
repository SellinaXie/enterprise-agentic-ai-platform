"""Typed V5 specialist handoffs and public-safe execution metadata."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.assessment import ComplexityLevel, RiskCategory, RiskSeverity, SolutionPattern


class SpecialistModel(BaseModel):
    """Closed base contract for every schema-constrained specialist output."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SpecialistConfidence(StrEnum):
    """Explainable qualitative confidence shared by all specialists."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MultiAgentName(StrEnum):
    """The four V5 agents; LangGraph itself remains the orchestrator."""

    EVIDENCE = "evidence"
    ARCHITECTURE = "architecture"
    RISK_GOVERNANCE = "risk_governance"
    SYNTHESIS = "synthesis"


class MultiAgentStatus(StrEnum):
    """Public lifecycle states for one specialist execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class MultiAgentTraceEventType(StrEnum):
    """Safe events that never contain prompts, private reasoning, or source text."""

    WORKFLOW_STARTED = "workflow_started"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    TOOL_AUTHORIZATION_DENIED = "tool_authorization_denied"
    DEGRADED_MODE = "degraded_mode"
    WORKFLOW_COMPLETED = "workflow_completed"


class MultiAgentTerminationReason(StrEnum):
    """Finite V5 outcomes returned only after successful synthesis."""

    COMPLETED = "completed"
    COMPLETED_DEGRADED = "completed_degraded"


class EvidenceItem(SpecialistModel):
    """One bounded evidence claim with explicit observed provenance."""

    claim: str = Field(min_length=1, max_length=1_000)
    supporting_document_ids: list[UUID] = Field(default_factory=list, max_length=20)
    supporting_chunk_ids: list[UUID] = Field(default_factory=list, max_length=20)
    relevance: str = Field(min_length=1, max_length=1_000)
    notes: str | None = Field(default=None, max_length=1_000)


class EvidenceBrief(SpecialistModel):
    """Evidence Agent output passed to both independent specialist branches."""

    summary: str = Field(min_length=1, max_length=4_000)
    evidence_items: list[EvidenceItem] = Field(default_factory=list, max_length=50)
    evidence_gaps: list[str] = Field(default_factory=list, max_length=50)
    confidence: SpecialistConfidence
    retrieved_document_ids: list[UUID] = Field(default_factory=list, max_length=100)
    retrieved_chunk_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_item_provenance(self) -> "EvidenceBrief":
        """Require every cited item identifier to be declared by the brief."""
        document_ids = set(self.retrieved_document_ids)
        chunk_ids = set(self.retrieved_chunk_ids)
        for item in self.evidence_items:
            if not set(item.supporting_document_ids).issubset(document_ids):
                raise ValueError("Evidence item references an undeclared document")
            if not set(item.supporting_chunk_ids).issubset(chunk_ids):
                raise ValueError("Evidence item references an undeclared chunk")
        return self

    @classmethod
    def unavailable(cls) -> "EvidenceBrief":
        """Return an explicit request-only handoff after Evidence Agent failure."""
        return cls(
            summary="External evidence analysis was unavailable; use assessment input only.",
            evidence_gaps=["External evidence retrieval and analysis did not complete."],
            confidence=SpecialistConfidence.LOW,
        )


class ArchitectureRecommendation(SpecialistModel):
    """Solution Architecture Agent output without final business-result ownership."""

    recommended_pattern: SolutionPattern
    architecture_summary: str = Field(min_length=1, max_length=4_000)
    components: list[str] = Field(default_factory=list, max_length=50)
    data_flow: list[str] = Field(default_factory=list, max_length=50)
    integrations: list[str] = Field(default_factory=list, max_length=50)
    complexity: ComplexityLevel
    implementation_assumptions: list[str] = Field(default_factory=list, max_length=50)
    alternatives_considered: list[str] = Field(default_factory=list, max_length=50)
    why_simpler_options_are_or_are_not_sufficient: str = Field(min_length=1, max_length=4_000)
    confidence: SpecialistConfidence


class GovernanceRisk(SpecialistModel):
    """One risk finding scoped to governance analysis."""

    category: RiskCategory
    description: str = Field(min_length=1, max_length=2_000)
    severity: RiskSeverity
    mitigation: str = Field(min_length=1, max_length=2_000)


class GovernanceOversight(SpecialistModel):
    """Human decision boundary recommended by the governance specialist."""

    review_required: bool
    decisions_requiring_review: list[str] = Field(default_factory=list, max_length=50)
    rationale: str = Field(min_length=1, max_length=2_000)


class RiskGovernanceReview(SpecialistModel):
    """Risk & Governance Agent output isolated from architecture conclusions."""

    overall_risk: RiskSeverity
    risks: list[GovernanceRisk] = Field(default_factory=list, max_length=50)
    required_controls: list[str] = Field(default_factory=list, max_length=50)
    human_oversight: GovernanceOversight
    auditability_requirements: list[str] = Field(default_factory=list, max_length=50)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=50)
    confidence: SpecialistConfidence


class MultiAgentStatuses(SpecialistModel):
    """Lifecycle state for exactly the four V5 agents."""

    evidence: MultiAgentStatus
    architecture: MultiAgentStatus
    risk_governance: MultiAgentStatus
    synthesis: MultiAgentStatus


class MultiAgentDurations(SpecialistModel):
    """Best-effort elapsed milliseconds without provider-sensitive details."""

    evidence: int | None = Field(default=None, ge=0)
    architecture: int | None = Field(default=None, ge=0)
    risk_governance: int | None = Field(default=None, ge=0)
    synthesis: int | None = Field(default=None, ge=0)


class MultiAgentErrors(SpecialistModel):
    """Safe application error codes only; no exception messages or stack traces."""

    evidence: str | None = Field(default=None, max_length=100)
    architecture: str | None = Field(default=None, max_length=100)
    risk_governance: str | None = Field(default=None, max_length=100)
    synthesis: str | None = Field(default=None, max_length=100)


class MultiAgentTraceEvent(SpecialistModel):
    """One compact orchestration event safe for JSONB persistence and API return."""

    sequence: int = Field(ge=0)
    timestamp: datetime
    agent: MultiAgentName | None = None
    event_type: MultiAgentTraceEventType
    summary: str = Field(min_length=1, max_length=300)
    tool_name: str | None = Field(default=None, max_length=100)
    error_code: str | None = Field(default=None, max_length=100)


class MultiAgentExecutionMetadata(SpecialistModel):
    """Safe V5 execution summary stored in the existing JSONB column."""

    execution_mode: Literal["multi_agent"] = "multi_agent"
    agents: list[MultiAgentName] = Field(
        default_factory=lambda: [
            MultiAgentName.EVIDENCE,
            MultiAgentName.ARCHITECTURE,
            MultiAgentName.RISK_GOVERNANCE,
            MultiAgentName.SYNTHESIS,
        ]
    )
    agent_statuses: MultiAgentStatuses
    agent_durations_ms: MultiAgentDurations
    agent_errors: MultiAgentErrors
    tools_used: list[str]
    tool_calls: int = Field(ge=0)
    degraded_mode: bool
    degradation_reasons: list[str]
    termination_reason: MultiAgentTerminationReason
    trace: list[MultiAgentTraceEvent]

    @model_validator(mode="after")
    def validate_agent_roster(self) -> "MultiAgentExecutionMetadata":
        expected = list(MultiAgentName)
        if self.agents != expected:
            raise ValueError("V5 execution metadata must list exactly the four agents")
        return self
