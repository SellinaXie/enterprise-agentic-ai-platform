"""Assessment request and response schemas."""

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.assessment import (
    AssessmentStatus,
    ComplexityLevel,
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


class AssessmentResponse(BaseModel):
    """Completed AI-generated assessment response."""

    assessment_id: UUID
    status: AssessmentStatus
    result: AssessmentResult
