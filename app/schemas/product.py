"""Product schemas supporting the V8C interface and governance-core endpoints."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.assessment import AssessmentStatus
from app.runtime.models import (
    CandidateVersionFeedback,
    HumanReviewStatus,
    OperationalTelemetry,
    QualityGateResult,
    ReviewActionName,
    RuntimeReasonCode,
    RuntimeRiskDecision,
    RuntimeRiskLevel,
)
from app.schemas.assessment import AssessmentResult


class ProductSchema(BaseModel):
    """Closed response contract for product-oriented read endpoints."""

    model_config = ConfigDict(extra="forbid")


class PrincipalResponse(ProductSchema):
    """Safe authenticated identity for role-aware product UX."""

    subject: str
    email: str | None
    display_name: str | None
    roles: list[str]
    issuer: str | None


class AssessmentListItem(ProductSchema):
    """Compact assessment row without full result or source content."""

    assessment_id: UUID
    company_name: str
    industry: str
    business_problem: str
    status: AssessmentStatus
    execution_mode: str | None
    created_by_subject: str | None
    runtime_decision: RuntimeRiskDecision | None
    risk_level: RuntimeRiskLevel | None
    reason_codes: list[RuntimeReasonCode] = Field(default_factory=list)
    review_status: HumanReviewStatus | None
    request_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class AssessmentListResponse(ProductSchema):
    """Bounded assessment page plus database-backed dashboard facets."""

    items: list[AssessmentListItem]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)
    status_counts: dict[str, int]
    runtime_decision_counts: dict[str, int]
    review_status_counts: dict[str, int]


class DeniedReviewAction(ProductSchema):
    """A review action the caller cannot take now, with the backend's reason code."""

    action: ReviewActionName
    code: str


class ReviewCandidateResponse(ProductSchema):
    """Validated candidate visible only across the reviewer authorization boundary."""

    assessment_id: UUID
    result: AssessmentResult
    execution: dict[str, Any] | None
    gate_result: QualityGateResult
    review_status: HumanReviewStatus
    telemetry: OperationalTelemetry
    revision_count: int = Field(ge=0)
    max_revisions: int = Field(ge=0)
    created_by_subject: str | None
    allowed_actions: list[ReviewActionName]
    denied_actions: list[DeniedReviewAction]


class RevisionSubmissionResponse(ProductSchema):
    """Outcome of regenerating a candidate from reviewer feedback."""

    assessment_id: UUID
    version_number: int = Field(ge=0)
    assessment_status: AssessmentStatus
    review_status: HumanReviewStatus
    revision_count: int = Field(ge=0)
    gate_result: QualityGateResult


class CandidateVersionItem(ProductSchema):
    """One gated candidate version for side-by-side comparison."""

    version_number: int = Field(ge=0)
    created_at: datetime
    execution_mode: str | None
    gate_result: QualityGateResult
    result: AssessmentResult
    feedback: CandidateVersionFeedback | None


class CandidateVersionsResponse(ProductSchema):
    """Every persisted candidate version of one assessment, oldest first."""

    assessment_id: UUID
    versions: list[CandidateVersionItem]


class PolicyFixedRule(ProductSchema):
    """A gate rule that is not configurable."""

    signal: RuntimeReasonCode
    decision: RuntimeRiskDecision


class SeparationOfDutiesPolicy(ProductSchema):
    """Whether creators are barred from deciding on their own assessments."""

    enforced: bool
    applies_to: list[ReviewActionName]


class GovernancePolicyResponse(ProductSchema):
    """Read-only view of the runtime risk policy in force."""

    policy_fingerprint: str
    runtime_risk_gate_enabled: bool
    risk_level_decisions: dict[RuntimeRiskLevel, RuntimeRiskDecision]
    review_triggers: dict[str, bool]
    block_rules: dict[str, bool]
    fixed_rules: list[PolicyFixedRule]
    max_human_revisions: int = Field(ge=0)
    separation_of_duties: SeparationOfDutiesPolicy
    reason_codes: list[RuntimeReasonCode]


class EvaluationModeSummary(ProductSchema):
    """One existing deterministic benchmark mode prepared for display."""

    mode: str
    synthetic: bool
    total_cases: int = Field(ge=0)
    evaluated_cases: int = Field(ge=0)
    aggregate_metrics: dict[str, Any]
    warnings: list[str]
    reproducibility_fingerprint: str | None = None


class EvaluationSummaryResponse(ProductSchema):
    """Network-free V7A and V7B aggregate results."""

    v7a: list[EvaluationModeSummary]
    v7b: list[EvaluationModeSummary]
    disclaimer: str
