"""Typed provider-neutral state for one V5 multi-agent graph execution."""

from datetime import datetime
from typing import TypedDict

from app.agents.models import AgentTerminationReason
from app.agents.multi_agent_models import (
    ArchitectureRecommendation,
    EvidenceBrief,
    MultiAgentExecutionMetadata,
    MultiAgentStatus,
    MultiAgentTraceEvent,
    RiskGovernanceReview,
)
from app.models.knowledge import RetrievedEvidence
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.tools.models import ObservedKnowledgeDocument, ToolHistoryEntry


class MultiAgentGraphState(TypedDict):
    """State keys are branch-specific so parallel updates never collide."""

    assessment_id: str
    request: AssessmentRequest
    started_at: datetime | None
    completed_at: datetime | None
    max_failures: int
    evidence_brief: EvidenceBrief | None
    retrieved_evidence: list[RetrievedEvidence]
    observed_documents: list[ObservedKnowledgeDocument]
    tool_history: list[ToolHistoryEntry]
    evidence_steps_used: int
    evidence_termination_reason: AgentTerminationReason | None
    architecture_recommendation: ArchitectureRecommendation | None
    risk_governance_review: RiskGovernanceReview | None
    final_result: AssessmentResult | None
    execution: MultiAgentExecutionMetadata | None
    evidence_status: MultiAgentStatus
    architecture_status: MultiAgentStatus
    risk_governance_status: MultiAgentStatus
    synthesis_status: MultiAgentStatus
    evidence_error: str | None
    architecture_error: str | None
    risk_governance_error: str | None
    synthesis_error: str | None
    evidence_duration_ms: int | None
    architecture_duration_ms: int | None
    risk_governance_duration_ms: int | None
    synthesis_duration_ms: int | None
    initialization_trace: list[MultiAgentTraceEvent]
    evidence_trace: list[MultiAgentTraceEvent]
    architecture_trace: list[MultiAgentTraceEvent]
    risk_governance_trace: list[MultiAgentTraceEvent]
    synthesis_trace: list[MultiAgentTraceEvent]
    validation_trace: list[MultiAgentTraceEvent]


def initialize_multi_agent_state(
    *,
    assessment_id: str,
    request: AssessmentRequest,
    max_failures: int,
) -> MultiAgentGraphState:
    """Create isolated state for exactly one assessment execution."""
    return MultiAgentGraphState(
        assessment_id=assessment_id,
        request=request,
        started_at=None,
        completed_at=None,
        max_failures=max_failures,
        evidence_brief=None,
        retrieved_evidence=[],
        observed_documents=[],
        tool_history=[],
        evidence_steps_used=0,
        evidence_termination_reason=None,
        architecture_recommendation=None,
        risk_governance_review=None,
        final_result=None,
        execution=None,
        evidence_status=MultiAgentStatus.PENDING,
        architecture_status=MultiAgentStatus.PENDING,
        risk_governance_status=MultiAgentStatus.PENDING,
        synthesis_status=MultiAgentStatus.PENDING,
        evidence_error=None,
        architecture_error=None,
        risk_governance_error=None,
        synthesis_error=None,
        evidence_duration_ms=None,
        architecture_duration_ms=None,
        risk_governance_duration_ms=None,
        synthesis_duration_ms=None,
        initialization_trace=[],
        evidence_trace=[],
        architecture_trace=[],
        risk_governance_trace=[],
        synthesis_trace=[],
        validation_trace=[],
    )
