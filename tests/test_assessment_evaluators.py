"""Formula-level V7B deterministic quality evaluator tests."""

from app.evaluation.assessment.dataset import load_assessment_dataset
from app.evaluation.assessment.evaluators import evaluate_assessment
from app.evaluation.assessment.models import (
    ArchitectureCharacteristic,
    AssessmentClaim,
    AssessmentClaimType,
    AssessmentEvaluationMode,
    ClaimSupport,
    ClaimSupportSource,
    EvaluationControlCategory,
    EvaluationGovernanceRequirement,
    EvaluationRiskCategory,
    EvaluationSeverity,
    IdentifiedRisk,
)


def _case(case_id: str):  # noqa: ANN202
    return next(item for item in load_assessment_dataset().cases if item.case_id == case_id)


def test_perfect_explicit_output_scores_all_supported_dimensions() -> None:
    case = _case("case01_customer_service_pii")
    output = case.fixtures[AssessmentEvaluationMode.SINGLE_AGENT]

    metrics, observations = evaluate_assessment(case, output)

    assert metrics.risk_recall == 1.0
    assert metrics.risk_precision == 1.0
    assert metrics.severity_consistency == 1.0
    assert metrics.control_coverage == 1.0
    assert metrics.governance_coverage == 1.0
    assert metrics.human_oversight_accuracy == 1.0
    assert metrics.architecture_fit_score == 1.0
    assert metrics.groundedness == 1.0
    assert metrics.unsupported_claim_rate == 0.0
    assert observations.unsupported_claim_ids == []


def test_partial_and_false_positive_risks_affect_recall_precision_and_severity() -> None:
    case = _case("case01_customer_service_pii")
    output = case.fixtures[AssessmentEvaluationMode.DETERMINISTIC].model_copy(
        update={
            "identified_risks": [
                IdentifiedRisk(
                    finding_id="expected_privacy",
                    category=EvaluationRiskCategory.PRIVACY,
                    severity=EvaluationSeverity.MEDIUM,
                ),
                IdentifiedRisk(
                    finding_id="unexpected_vendor",
                    category=EvaluationRiskCategory.THIRD_PARTY_VENDOR_RISK,
                    severity=EvaluationSeverity.HIGH,
                ),
            ]
        }
    )

    metrics, observations = evaluate_assessment(case, output)

    assert metrics.risk_recall == 0.25
    assert metrics.risk_precision == 0.5
    assert metrics.severity_consistency == 0.0
    assert observations.unacceptable_risks_identified == [
        EvaluationRiskCategory.THIRD_PARTY_VENDOR_RISK
    ]


def test_missing_controls_and_governance_are_measured_from_explicit_categories() -> None:
    case = _case("case01_customer_service_pii")
    output = case.fixtures[AssessmentEvaluationMode.SINGLE_AGENT].model_copy(
        update={
            "recommended_controls": [EvaluationControlCategory.HUMAN_APPROVAL],
            "governance_requirements": [EvaluationGovernanceRequirement.HUMAN_DECISION_AUTHORITY],
        }
    )

    metrics, observations = evaluate_assessment(case, output)

    assert metrics.control_coverage == 1 / 6
    assert metrics.governance_coverage == 0.25
    assert len(observations.missing_controls) == 5
    assert len(observations.missing_governance_requirements) == 3


def test_human_oversight_detects_required_and_unnecessary_recommendations() -> None:
    required = _case("case01_customer_service_pii")
    required_output = required.fixtures[AssessmentEvaluationMode.SINGLE_AGENT].model_copy(
        update={"human_oversight_recommended": False}
    )
    simple = _case("case10_simple_rules_workflow")
    simple_output = simple.fixtures[AssessmentEvaluationMode.SINGLE_AGENT]

    assert evaluate_assessment(required, required_output)[0].human_oversight_accuracy == 0.0
    assert evaluate_assessment(simple, simple_output)[0].human_oversight_accuracy == 0.0


def test_architecture_fit_and_over_engineering_are_separate_transparent_metrics() -> None:
    case = _case("case10_simple_rules_workflow")
    simple = case.fixtures[AssessmentEvaluationMode.DETERMINISTIC]
    excessive = case.fixtures[AssessmentEvaluationMode.MULTI_AGENT]

    simple_metrics = evaluate_assessment(case, simple)[0]
    excessive_metrics = evaluate_assessment(case, excessive)[0]

    assert simple_metrics.architecture_fit_score == 1.0
    assert simple_metrics.over_engineering_avoidance == 1.0
    assert excessive_metrics.architecture_fit_score == 0.0
    assert excessive_metrics.over_engineering_avoidance == 0.0


def test_missing_and_invalid_citations_create_unsupported_claims() -> None:
    case = _case("case01_customer_service_pii")
    base = case.fixtures[AssessmentEvaluationMode.SINGLE_AGENT]
    missing = base.model_copy(
        update={
            "claims": [
                AssessmentClaim(
                    claim_id="c01_policy",
                    claim_type=AssessmentClaimType.CONTROL,
                    summary="A policy claim without its required citation.",
                )
            ]
        }
    )
    invalid = base.model_copy(
        update={
            "claims": [
                AssessmentClaim(
                    claim_id="c01_policy",
                    claim_type=AssessmentClaimType.CONTROL,
                    summary="A policy claim with an invented citation.",
                    supports=[
                        ClaimSupport(
                            source=ClaimSupportSource.RETRIEVED_EVIDENCE,
                            reference_id="invented-reference",
                        )
                    ],
                )
            ]
        }
    )

    missing_metrics, missing_observations = evaluate_assessment(case, missing)
    invalid_metrics, invalid_observations = evaluate_assessment(case, invalid)

    assert missing_metrics.unsupported_claim_rate == 1.0
    assert missing_observations.missing_citation_claim_ids == ["c01_policy"]
    assert invalid_metrics.groundedness == 0.0
    assert invalid_observations.invalid_citation_claim_ids == ["c01_policy"]


def test_invented_claim_is_unsupported_even_when_it_names_a_support_source() -> None:
    case = _case("case01_customer_service_pii")
    output = case.fixtures[AssessmentEvaluationMode.SINGLE_AGENT].model_copy(
        update={
            "claims": [
                AssessmentClaim(
                    claim_id="invented_policy_claim",
                    claim_type=AssessmentClaimType.GOVERNANCE,
                    summary="An undeclared policy requirement.",
                    supports=[ClaimSupport(source=ClaimSupportSource.ASSESSMENT_INPUT)],
                )
            ]
        }
    )

    metrics, observations = evaluate_assessment(case, output)

    assert metrics.groundedness == 0.0
    assert metrics.unsupported_claim_rate == 1.0
    assert observations.unsupported_claim_ids == ["invented_policy_claim"]


def test_invented_specialist_finding_cannot_ground_a_claim() -> None:
    case = _case("case01_customer_service_pii")
    output = case.fixtures[AssessmentEvaluationMode.MULTI_AGENT].model_copy(
        update={
            "claims": [
                AssessmentClaim(
                    claim_id="c01_policy",
                    claim_type=AssessmentClaimType.CONTROL,
                    summary="A claim tied to a specialist finding that was never emitted.",
                    supports=[
                        ClaimSupport(
                            source=ClaimSupportSource.SPECIALIST_OUTPUT,
                            reference_id="f01_invented",
                        )
                    ],
                )
            ]
        }
    )

    metrics, observations = evaluate_assessment(case, output)

    assert metrics.unsupported_claim_rate == 1.0
    assert observations.unsupported_claim_ids == ["c01_policy"]


def test_required_abstention_scores_each_required_behavior() -> None:
    case = _case("case09_insufficient_information")
    correct = case.fixtures[AssessmentEvaluationMode.SINGLE_AGENT]
    partial = correct.model_copy(
        update={
            "uncertainty_acknowledged": False,
            "validation_recommended": False,
        }
    )

    assert evaluate_assessment(case, correct)[0].appropriate_abstention_rate == 1.0
    assert evaluate_assessment(case, partial)[0].appropriate_abstention_rate == 1 / 3


def test_unnecessary_abstention_is_penalized_when_evidence_is_sufficient() -> None:
    case = _case("case02_confidential_internal_rag")
    output = case.fixtures[AssessmentEvaluationMode.SINGLE_AGENT].model_copy(
        update={"abstained_from_unsupported_conclusion": True}
    )

    assert evaluate_assessment(case, output)[0].appropriate_abstention_rate == 0.0


def test_specialist_preservation_disagreement_and_degradation_are_explicit() -> None:
    conflict = _case("case03_external_tool_access")
    conflict_output = conflict.fixtures[AssessmentEvaluationMode.MULTI_AGENT]
    degraded = _case("case09_insufficient_information")
    degraded_output = degraded.fixtures[AssessmentEvaluationMode.MULTI_AGENT]

    conflict_metrics = evaluate_assessment(conflict, conflict_output)[0]
    degraded_metrics = evaluate_assessment(degraded, degraded_output)[0]

    assert conflict_metrics.specialist_preservation == 1.0
    assert conflict_metrics.synthesis_transparency == 1.0
    assert degraded_metrics.specialist_preservation == 1.0
    assert degraded_metrics.synthesis_transparency == 1.0


def test_graph_architecture_characteristic_is_valid_but_not_implicitly_expected() -> None:
    case = _case("case02_confidential_internal_rag")
    output = case.fixtures[AssessmentEvaluationMode.SINGLE_AGENT].model_copy(
        update={
            "architecture_characteristics": [ArchitectureCharacteristic.GRAPH_RETRIEVAL_APPROPRIATE]
        }
    )

    metrics, observations = evaluate_assessment(case, output)

    assert metrics.architecture_fit_score == 0.0
    assert len(observations.missing_architecture_characteristics) == 2
