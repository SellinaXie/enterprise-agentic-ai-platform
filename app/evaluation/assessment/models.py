"""Typed contracts for the synthetic V7B assessment-quality benchmark."""

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from app.evaluation.models import EvaluationModel


class AssessmentEvaluationMode(StrEnum):
    """Existing assessment execution paths compared by V7B."""

    DETERMINISTIC = "deterministic"
    SINGLE_AGENT = "single_agent"
    MULTI_AGENT = "multi_agent"


class AssessmentScenarioCategory(StrEnum):
    """Finite scenario families represented by the synthetic benchmark."""

    CUSTOMER_SERVICE_PII = "customer_service_pii"
    CONFIDENTIAL_INTERNAL_RAG = "confidential_internal_rag"
    EXTERNAL_TOOL_ACCESS = "external_tool_access"
    HIGH_IMPACT_DECISION = "high_impact_decision"
    THIRD_PARTY_VENDOR = "third_party_vendor"
    COMPLIANCE_REVIEW = "compliance_review"
    HUMAN_OPERATED_RECOMMENDATION = "human_operated_recommendation"
    LOW_RISK_PRODUCTIVITY = "low_risk_productivity"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    SIMPLE_DETERMINISTIC = "simple_deterministic"


class EvaluationRiskCategory(StrEnum):
    """Evaluation taxonomy, not a regulatory or GRC standard."""

    PRIVACY = "privacy"
    SECURITY = "security"
    MODEL_RISK = "model_risk"
    HALLUCINATION_GROUNDING = "hallucination_grounding"
    COMPLIANCE = "compliance"
    OPERATIONAL_RISK = "operational_risk"
    ACCESS_CONTROL = "access_control"
    DATA_GOVERNANCE = "data_governance"
    THIRD_PARTY_VENDOR_RISK = "third_party_vendor_risk"
    EXPLAINABILITY = "explainability"
    HUMAN_OVERSIGHT = "human_oversight"
    MONITORING = "monitoring"
    AUDITABILITY = "auditability"


class EvaluationControlCategory(StrEnum):
    """Small controlled vocabulary of common enterprise AI controls."""

    RETRIEVAL_GROUNDING = "retrieval_grounding"
    ROLE_BASED_ACCESS_CONTROL = "role_based_access_control"
    LEAST_PRIVILEGE = "least_privilege"
    TOOL_ALLOWLISTING = "tool_allowlisting"
    HUMAN_APPROVAL = "human_approval"
    ESCALATION = "escalation"
    AUDIT_LOGGING = "audit_logging"
    DATA_MINIMIZATION = "data_minimization"
    MODEL_MONITORING = "model_monitoring"
    OUTPUT_VALIDATION = "output_validation"
    FALLBACK_BEHAVIOR = "fallback_behavior"
    VERSIONING = "versioning"
    APPROVAL_GATES = "approval_gates"
    VENDOR_DUE_DILIGENCE = "vendor_due_diligence"
    INCIDENT_RESPONSE = "incident_response"


class EvaluationGovernanceRequirement(StrEnum):
    """Reviewable governance expectations used only by this benchmark."""

    ACCOUNTABLE_OWNER = "accountable_owner"
    DOCUMENTED_USE_CASE = "documented_use_case"
    RISK_REVIEW = "risk_review"
    DATA_USE_APPROVAL = "data_use_approval"
    VENDOR_OVERSIGHT = "vendor_oversight"
    HUMAN_DECISION_AUTHORITY = "human_decision_authority"
    AUDIT_RECORD = "audit_record"
    PERIODIC_REVIEW = "periodic_review"


class ArchitectureCharacteristic(StrEnum):
    """Explicit architecture properties assessed without keyword inference."""

    DETERMINISTIC_SUFFICIENT = "deterministic_sufficient"
    RAG_APPROPRIATE = "rag_appropriate"
    GRAPH_RETRIEVAL_APPROPRIATE = "graph_retrieval_appropriate"
    AGENT_WORKFLOW_JUSTIFIED = "agent_workflow_justified"
    MULTI_AGENT_JUSTIFIED = "multi_agent_justified"
    MULTI_AGENT_UNNECESSARY = "multi_agent_unnecessary"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    EXTERNAL_TOOL_PERMISSIONS_CONSTRAINED = "external_tool_permissions_constrained"
    SIMPLER_WORKFLOW_PREFERRED = "simpler_workflow_preferred"


class EvaluationSeverity(StrEnum):
    """Simple severity scale for benchmark consistency checks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AbstentionExpectation(StrEnum):
    """Whether a case has enough evidence for a specific conclusion."""

    REQUIRED = "required"
    NOT_REQUIRED = "not_required"


class ClaimSupportSource(StrEnum):
    """Allowed, inspectable origins for one normalized assessment claim."""

    ASSESSMENT_INPUT = "assessment_input"
    RETRIEVED_EVIDENCE = "retrieved_evidence"
    SPECIALIST_OUTPUT = "specialist_output"
    SYSTEM_KNOWLEDGE = "system_knowledge"


class AssessmentClaimType(StrEnum):
    """Claim families evaluated for source support."""

    FACT = "fact"
    RISK = "risk"
    CONTROL = "control"
    GOVERNANCE = "governance"
    ARCHITECTURE = "architecture"


class AssessmentRunStatus(StrEnum):
    """Transparent fixture or live execution outcome."""

    COMPLETED = "completed"
    DEGRADED = "degraded"
    FAILED = "failed"


class ExpectedRisk(EvaluationModel):
    """One important expected risk and its benchmark severity."""

    category: EvaluationRiskCategory
    severity: EvaluationSeverity


class ExpectedEvidenceRequirement(EvaluationModel):
    """Allowed support paths for one claim identity."""

    claim_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    allowed_sources: set[ClaimSupportSource] = Field(min_length=1)
    allowed_reference_ids: list[str] = Field(default_factory=list)
    allowed_specialist_finding_ids: list[str] = Field(default_factory=list)
    allowed_system_knowledge_categories: list[str] = Field(default_factory=list)
    citation_required: bool = False


class ExpectedAbstentionBehavior(EvaluationModel):
    """Reviewable uncertainty behavior for evidence-sufficient or sparse cases."""

    expectation: AbstentionExpectation
    uncertainty_acknowledgment_required: bool = False
    validation_recommendation_required: bool = False

    @model_validator(mode="after")
    def validate_required_behavior(self) -> Self:
        if self.expectation == AbstentionExpectation.REQUIRED and not (
            self.uncertainty_acknowledgment_required and self.validation_recommendation_required
        ):
            raise ValueError("required abstention must require uncertainty and validation")
        return self


class IdentifiedRisk(EvaluationModel):
    """One normalized risk emitted by an evaluated assessment."""

    finding_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    category: EvaluationRiskCategory
    severity: EvaluationSeverity


class ClaimSupport(EvaluationModel):
    """One asserted support reference; validity is decided by the benchmark."""

    source: ClaimSupportSource
    reference_id: str | None = Field(default=None, min_length=1, max_length=200)
    system_knowledge_category: str | None = Field(default=None, min_length=1, max_length=100)


class AssessmentClaim(EvaluationModel):
    """A concise evaluable claim without private reasoning."""

    claim_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    claim_type: AssessmentClaimType
    summary: str = Field(min_length=1, max_length=500)
    supports: list[ClaimSupport] = Field(default_factory=list, max_length=10)


class SpecialistEvaluationTrace(EvaluationModel):
    """Normalized observations from the four existing V5 specialists."""

    available_finding_ids: list[str] = Field(default_factory=list)
    important_finding_ids: list[str] = Field(default_factory=list)
    disagreement_ids: list[str] = Field(default_factory=list)
    unavailable_specialists: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_findings(self) -> Self:
        _require_unique("specialist finding IDs", self.available_finding_ids)
        _require_unique("important specialist finding IDs", self.important_finding_ids)
        _require_unique("specialist disagreement IDs", self.disagreement_ids)
        if not set(self.important_finding_ids).issubset(self.available_finding_ids):
            raise ValueError("important specialist findings must be available")
        return self


class AssessmentEvaluationOutput(EvaluationModel):
    """Shared normalized final-output contract for all three modes."""

    summary: str = Field(min_length=1, max_length=1_000)
    identified_risks: list[IdentifiedRisk] = Field(default_factory=list)
    recommended_controls: list[EvaluationControlCategory] = Field(default_factory=list)
    governance_requirements: list[EvaluationGovernanceRequirement] = Field(default_factory=list)
    architecture_characteristics: list[ArchitectureCharacteristic] = Field(default_factory=list)
    human_oversight_recommended: bool
    uncertainty_acknowledged: bool
    abstained_from_unsupported_conclusion: bool
    validation_recommended: bool
    claims: list[AssessmentClaim] = Field(default_factory=list)
    run_status: AssessmentRunStatus = AssessmentRunStatus.COMPLETED
    degradation_reasons: list[str] = Field(default_factory=list)
    specialists: SpecialistEvaluationTrace | None = None
    preserved_specialist_finding_ids: list[str] = Field(default_factory=list)
    surfaced_disagreement_ids: list[str] = Field(default_factory=list)
    degraded_state_acknowledged: bool = False

    @model_validator(mode="after")
    def validate_output(self) -> Self:
        _require_unique(
            "identified risk categories", [item.category for item in self.identified_risks]
        )
        _require_unique("recommended controls", self.recommended_controls)
        _require_unique("governance requirements", self.governance_requirements)
        _require_unique("architecture characteristics", self.architecture_characteristics)
        _require_unique("claim IDs", [item.claim_id for item in self.claims])
        _require_unique("preserved specialist finding IDs", self.preserved_specialist_finding_ids)
        _require_unique("surfaced disagreement IDs", self.surfaced_disagreement_ids)
        if self.run_status == AssessmentRunStatus.DEGRADED and not self.degradation_reasons:
            raise ValueError("degraded outputs require a reason")
        if self.run_status == AssessmentRunStatus.COMPLETED and self.degradation_reasons:
            raise ValueError("completed outputs cannot declare degradation reasons")
        if self.specialists is None and (
            self.preserved_specialist_finding_ids or self.surfaced_disagreement_ids
        ):
            raise ValueError("specialist synthesis observations require specialist outputs")
        return self


class AssessmentEvaluationCase(EvaluationModel):
    """One synthetic scenario with explicit expected quality characteristics."""

    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    title: str = Field(min_length=1, max_length=300)
    scenario_category: AssessmentScenarioCategory
    business_context: str = Field(min_length=1, max_length=4_000)
    industry: str = Field(min_length=1, max_length=120)
    business_problem: str = Field(min_length=1, max_length=2_000)
    expected_risks: list[ExpectedRisk] = Field(min_length=1)
    unacceptable_risks: list[EvaluationRiskCategory] = Field(default_factory=list)
    expected_controls: list[EvaluationControlCategory] = Field(min_length=1)
    expected_governance_requirements: list[EvaluationGovernanceRequirement] = Field(min_length=1)
    expected_architecture_characteristics: list[ArchitectureCharacteristic] = Field(min_length=1)
    human_oversight_expected: bool
    available_evidence_ids: list[str] = Field(default_factory=list)
    evidence_requirements: list[ExpectedEvidenceRequirement] = Field(min_length=1)
    abstention: ExpectedAbstentionBehavior
    evaluation_notes: str = Field(min_length=1, max_length=1_000)
    fixtures: dict[AssessmentEvaluationMode, AssessmentEvaluationOutput]

    @model_validator(mode="after")
    def validate_case_integrity(self) -> Self:
        risk_categories = [item.category for item in self.expected_risks]
        _require_unique("expected risk categories", risk_categories)
        _require_unique("unacceptable risks", self.unacceptable_risks)
        if set(risk_categories) & set(self.unacceptable_risks):
            raise ValueError("expected and unacceptable risks must be disjoint")
        _require_unique("expected controls", self.expected_controls)
        _require_unique("expected governance requirements", self.expected_governance_requirements)
        _require_unique(
            "expected architecture characteristics", self.expected_architecture_characteristics
        )
        _require_unique("available evidence IDs", self.available_evidence_ids)
        _require_unique(
            "evidence claim IDs", [item.claim_id for item in self.evidence_requirements]
        )
        available_evidence = set(self.available_evidence_ids)
        for requirement in self.evidence_requirements:
            if not set(requirement.allowed_reference_ids).issubset(available_evidence):
                raise ValueError("claim requirement references unavailable evidence")
            if requirement.citation_required and not requirement.allowed_reference_ids:
                raise ValueError("citation-required claims need an allowed evidence reference")
        if set(self.fixtures) != set(AssessmentEvaluationMode):
            raise ValueError("every benchmark case requires all three execution modes")
        return self


class AssessmentEvaluationDataset(EvaluationModel):
    """Versioned synthetic scenarios and deterministic mode fixtures."""

    dataset_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=1_000)
    synthetic: bool
    taxonomy_notice: str = Field(min_length=1, max_length=1_000)
    cases: list[AssessmentEvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dataset_integrity(self) -> Self:
        if not self.synthetic:
            raise ValueError("V7B benchmark must be explicitly synthetic")
        _require_unique("assessment case IDs", [item.case_id for item in self.cases])
        _require_unique("scenario categories", [item.scenario_category for item in self.cases])
        return self


class AssessmentQualityMetrics(EvaluationModel):
    """Transparent V7B metrics; unsupported dimensions remain null."""

    risk_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    risk_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    severity_consistency: float | None = Field(default=None, ge=0.0, le=1.0)
    control_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    governance_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    human_oversight_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    architecture_fit_score: float | None = Field(default=None, ge=0.0, le=1.0)
    over_engineering_avoidance: float | None = Field(default=None, ge=0.0, le=1.0)
    groundedness: float | None = Field(default=None, ge=0.0, le=1.0)
    unsupported_claim_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    appropriate_abstention_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    specialist_preservation: float | None = Field(default=None, ge=0.0, le=1.0)
    synthesis_transparency: float | None = Field(default=None, ge=0.0, le=1.0)


class AssessmentQualityObservations(EvaluationModel):
    """Per-case facts supporting calculated metrics without source text or CoT."""

    identified_risks: list[IdentifiedRisk] = Field(default_factory=list)
    missing_risks: list[EvaluationRiskCategory] = Field(default_factory=list)
    unexpected_risks: list[EvaluationRiskCategory] = Field(default_factory=list)
    recommended_controls: list[EvaluationControlCategory] = Field(default_factory=list)
    missing_controls: list[EvaluationControlCategory] = Field(default_factory=list)
    governance_requirements: list[EvaluationGovernanceRequirement] = Field(default_factory=list)
    missing_governance_requirements: list[EvaluationGovernanceRequirement] = Field(
        default_factory=list
    )
    architecture_characteristics: list[ArchitectureCharacteristic] = Field(default_factory=list)
    missing_architecture_characteristics: list[ArchitectureCharacteristic] = Field(
        default_factory=list
    )
    unsupported_claim_ids: list[str] = Field(default_factory=list)
    missing_citation_claim_ids: list[str] = Field(default_factory=list)
    invalid_citation_claim_ids: list[str] = Field(default_factory=list)
    unacceptable_risks_identified: list[EvaluationRiskCategory] = Field(default_factory=list)
    human_oversight_expected: bool
    human_oversight_recommended: bool
    abstention_expected: AbstentionExpectation
    uncertainty_acknowledged: bool
    abstained_from_unsupported_conclusion: bool
    validation_recommended: bool
    run_status: AssessmentRunStatus
    degradation_reasons: list[str] = Field(default_factory=list)


class JudgeDimension(StrEnum):
    """Narrow qualitative dimensions available to the optional judge."""

    GROUNDEDNESS = "groundedness"
    RISK_REASONING_QUALITY = "risk_reasoning_quality"
    MITIGATION_USEFULNESS = "mitigation_usefulness"
    ARCHITECTURE_APPROPRIATENESS = "architecture_appropriateness"
    GOVERNANCE_COMPLETENESS = "governance_completeness"
    CLARITY_ACTIONABILITY = "clarity_actionability"


class JudgeDimensionScore(EvaluationModel):
    """One bounded qualitative score and concise summary rationale."""

    dimension: JudgeDimension
    score: int = Field(ge=1, le=5)
    rationale: str = Field(min_length=1, max_length=500)


class JudgeFinding(EvaluationModel):
    """Concise judge observation, never private chain-of-thought."""

    finding_type: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=500)


class JudgeUsage(EvaluationModel):
    """Optional provider token counters when exposed directly by the SDK."""

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class LLMJudgeResult(EvaluationModel):
    """Strict optional model-based evaluation contract."""

    dimensions: list[JudgeDimensionScore]
    findings: list[JudgeFinding] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0.0, le=1.0)
    usage: JudgeUsage | None = None

    @model_validator(mode="after")
    def validate_dimensions(self) -> Self:
        dimensions = [item.dimension for item in self.dimensions]
        _require_unique("judge dimensions", dimensions)
        if set(dimensions) != set(JudgeDimension):
            raise ValueError("judge output must score every declared dimension")
        return self


class AssessmentCaseEvaluationResult(EvaluationModel):
    """One mode/case result with transparent failures and optional judge output."""

    case_id: str
    scenario_category: AssessmentScenarioCategory
    mode: AssessmentEvaluationMode
    failed: bool = False
    error_code: str | None = None
    metrics: AssessmentQualityMetrics
    observations: AssessmentQualityObservations | None = None
    judge: LLMJudgeResult | None = None


class AssessmentEvaluationConfiguration(EvaluationModel):
    """Non-secret V7B execution snapshot."""

    execution_profile: str
    judge_enabled: bool
    judge_model: str | None = None
    deterministic_contract_version: str = "v7b-1"


class AssessmentEvaluationReport(EvaluationModel):
    """Machine-readable output for one assessment execution mode."""

    generated_at: datetime
    dataset_id: str
    dataset_version: str
    synthetic: bool
    mode: AssessmentEvaluationMode
    total_cases: int = Field(ge=0)
    evaluated_cases: int = Field(ge=0)
    skipped_cases: list[str] = Field(default_factory=list)
    failed_cases: list[str] = Field(default_factory=list)
    degraded_cases: list[str] = Field(default_factory=list)
    aggregate_metrics: AssessmentQualityMetrics
    cases: list[AssessmentCaseEvaluationResult]
    configuration: AssessmentEvaluationConfiguration
    llm_judge_calls: int = Field(ge=0)
    reproducibility_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    warnings: list[str] = Field(default_factory=list)


class AssessmentComparisonRow(EvaluationModel):
    """One aligned calculated metric across available modes."""

    metric: str
    values: dict[AssessmentEvaluationMode, float | None]


class AssessmentModeComparison(EvaluationModel):
    """Portfolio-ready V7B comparison with no hardcoded winner."""

    generated_at: datetime
    dataset_id: str
    dataset_version: str
    synthetic: bool
    modes: list[AssessmentEvaluationMode]
    rows: list[AssessmentComparisonRow]
    key_tradeoffs: list[str]
    best_mode_by_case: dict[str, list[AssessmentEvaluationMode]]
    benchmark_scope: dict[str, object]
    warnings: list[str] = Field(default_factory=list)


def _require_unique(label: str, values: list[object]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
