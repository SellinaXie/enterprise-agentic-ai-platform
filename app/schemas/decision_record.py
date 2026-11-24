"""Exportable decision record: who decided what, when, on which evidence and policy."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.assessment import AssessmentStatus
from app.runtime.models import (
    CandidateVersionFeedback,
    HumanReviewAction,
    HumanReviewStatus,
    QualityGateResult,
    RuntimeReasonCode,
)
from app.schemas.assessment import AssessmentRequest, AssessmentResult, SourceReference


class DecisionRecordSchema(BaseModel):
    """Closed contract; every field comes from persisted state."""

    model_config = ConfigDict(extra="forbid")


class DecisionRecordInput(DecisionRecordSchema):
    request: AssessmentRequest
    created_by_subject: str | None
    created_at: datetime


class DecisionRecordRouting(DecisionRecordSchema):
    preferred_execution_mode: str | None
    execution_mode: str | None
    routing_reason_codes: list[str]
    fallback_reason_codes: list[str]


class DecisionRecordCandidateVersion(DecisionRecordSchema):
    version_number: int
    created_at: datetime
    execution_mode: str | None
    gate_result: QualityGateResult
    policy_fingerprint: str | None
    feedback: CandidateVersionFeedback | None


class DecisionRecordReview(DecisionRecordSchema):
    review_id: UUID
    action: HumanReviewAction
    previous_status: HumanReviewStatus
    new_status: HumanReviewStatus
    reviewer_subject: str | None
    reviewer_role: str | None
    reviewer_issuer: str | None
    comment: str | None
    reason_codes: list[RuntimeReasonCode]
    revision_number: int
    created_at: datetime


class DecisionRecordOutcome(DecisionRecordSchema):
    status: AssessmentStatus
    result: AssessmentResult | None
    error_code: str | None
    completed_at: datetime | None


class DecisionRecordResponse(DecisionRecordSchema):
    """Version 1 of the export; ``record_fingerprint`` excludes ``generated_at``."""

    record_version: Literal[1] = 1
    assessment_id: UUID
    generated_at: datetime
    record_fingerprint: str
    current_policy_fingerprint: str | None
    input: DecisionRecordInput
    routing: DecisionRecordRouting
    evidence_source: Literal["final_result", "latest_candidate", "none"]
    evidence: list[SourceReference]
    candidate_versions: list[DecisionRecordCandidateVersion]
    reviews: list[DecisionRecordReview]
    outcome: DecisionRecordOutcome


def routing_from_execution(execution: dict[str, Any] | None) -> DecisionRecordRouting:
    """Read routing fields from any persisted execution-metadata shape."""
    execution = execution or {}

    def _codes(key: str) -> list[str]:
        value = execution.get(key)
        return [str(item) for item in value] if isinstance(value, list) else []

    def _text(key: str) -> str | None:
        value = execution.get(key)
        return value if isinstance(value, str) else None

    return DecisionRecordRouting(
        preferred_execution_mode=_text("preferred_execution_mode"),
        execution_mode=_text("execution_mode"),
        routing_reason_codes=_codes("routing_reason_codes"),
        fallback_reason_codes=_codes("fallback_reason_codes"),
    )
