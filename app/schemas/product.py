"""Read-only product schemas supporting the V8C interface."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.assessment import AssessmentStatus
from app.runtime.models import (
    HumanReviewStatus,
    OperationalTelemetry,
    QualityGateResult,
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
