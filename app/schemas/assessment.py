"""Assessment request and response schemas."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.models import AssessmentExecutionMetadata, DeterministicExecutionMetadata
from app.agents.multi_agent_models import MultiAgentExecutionMetadata
from app.models.assessment import (
    AssessmentStatus,
    ComplexityLevel,
    ExternalEvidenceStatus,
    PriorityLevel,
    RiskCategory,
    RiskSeverity,
    SolutionPattern,
    SuitabilityLevel,
)

ContextItem = Annotated[str, Field(min_length=1, max_length=500)]


class AssessmentRequest(BaseModel):
    """Input describing an enterprise business process and desired change."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=200)
    organization_description: str | None = Field(default=None, min_length=1, max_length=2_000)
    industry: str = Field(min_length=1, max_length=120)
    business_problem: str = Field(min_length=1, max_length=2_000)
    current_process: str | None = Field(default=None, min_length=1, max_length=4_000)
    pain_points: list[ContextItem] = Field(default_factory=list, max_length=20)
    desired_outcome: str = Field(min_length=1, max_length=2_000)
    constraints: list[ContextItem] = Field(default_factory=list, max_length=20)
    additional_context: str | None = Field(default=None, min_length=1, max_length=4_000)


class StructuredOutputModel(BaseModel):
    """Base model for schema-constrained LLM output."""

    model_config = ConfigDict(extra="forbid")


class ProblemAnalysis(StructuredOutputModel):
    """Analysis of the submitted process and its central weaknesses."""

    core_problem: str
    current_process_weaknesses: list[str]
    key_bottlenecks: list[str]


class AISuitability(StructuredOutputModel):
    """Assessment of whether AI is appropriate for the supplied problem."""

    level: SuitabilityLevel
    rationale: str


class RecommendedUseCase(StructuredOutputModel):
    """A concrete AI or automation opportunity."""

    name: str
    description: str
    expected_business_value: str
    complexity: ComplexityLevel
    priority: PriorityLevel


class RecommendedSolution(StructuredOutputModel):
    """The simplest high-level solution pattern that fits the evidence."""

    pattern: SolutionPattern
    description: str
    rationale: str


class AssessmentRisk(StructuredOutputModel):
    """A delivery or operational risk and its proposed mitigation."""

    category: RiskCategory
    description: str
    severity: RiskSeverity
    mitigation: str


class HumanOversight(StructuredOutputModel):
    """Recommended human review requirements."""

    review_recommended: bool
    decisions_requiring_review: list[str]
    rationale: str


class NextStep(StructuredOutputModel):
    """A practical action ordered by its numeric priority."""

    priority: int
    action: str
    rationale: str


class SourceReference(StructuredOutputModel):
    """Reference to retrieved evidence without reproducing source content."""

    document_id: UUID
    chunk_id: UUID
    document_title: str


class AssessmentResult(StructuredOutputModel):
    """Complete schema-constrained enterprise AI assessment."""

    executive_summary: str
    problem_analysis: ProblemAnalysis
    ai_suitability: AISuitability
    recommended_use_cases: list[RecommendedUseCase]
    recommended_solution: RecommendedSolution
    risks: list[AssessmentRisk]
    human_oversight: HumanOversight
    next_steps: list[NextStep]
    assumptions: list[str]
    information_gaps: list[str]
    external_evidence_status: ExternalEvidenceStatus = ExternalEvidenceStatus.NOT_RETRIEVED
    source_references: list[SourceReference] = Field(default_factory=list)


class AssessmentFailure(BaseModel):
    """Safe persisted failure details."""

    code: str
    message: str


class AssessmentResponse(BaseModel):
    """Persisted assessment state returned by create and retrieval endpoints."""

    assessment_id: UUID
    status: AssessmentStatus
    input: AssessmentRequest
    result: AssessmentResult | None
    execution: (
        DeterministicExecutionMetadata
        | AssessmentExecutionMetadata
        | MultiAgentExecutionMetadata
        | None
    ) = None
    error: AssessmentFailure | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    @model_validator(mode="after")
    def validate_lifecycle_payloads(self) -> "AssessmentResponse":
        """Reject completed or failed responses with inconsistent persisted state."""
        if self.status == AssessmentStatus.COMPLETED:
            if self.result is None or self.completed_at is None or self.error is not None:
                raise ValueError("Completed assessments require a result and completion timestamp")
        elif self.status == AssessmentStatus.FAILED and (
            self.result is not None or self.error is None
        ):
            raise ValueError("Failed assessments require an error and no result")
        elif self.status == AssessmentStatus.PENDING_REVIEW and (
            self.result is not None or self.error is not None or self.completed_at is not None
        ):
            raise ValueError(
                "Pending-review assessments require no public result, error, or completion time"
            )
        return self
