"""Deterministic V7B quality evaluators over explicit normalized contracts."""

from collections.abc import Iterable, Sequence

from app.evaluation.assessment.models import (
    AbstentionExpectation,
    ArchitectureCharacteristic,
    AssessmentEvaluationCase,
    AssessmentEvaluationOutput,
    AssessmentQualityMetrics,
    AssessmentQualityObservations,
    ClaimSupport,
    ClaimSupportSource,
    ExpectedEvidenceRequirement,
)


def evaluate_assessment(
    case: AssessmentEvaluationCase,
    output: AssessmentEvaluationOutput,
) -> tuple[AssessmentQualityMetrics, AssessmentQualityObservations]:
    """Calculate transparent set, provenance, uncertainty, and synthesis metrics."""
    expected_risks = {item.category: item for item in case.expected_risks}
    identified_risks = {item.category: item for item in output.identified_risks}
    matched_risks = set(expected_risks) & set(identified_risks)
    unexpected_risks = set(identified_risks) - set(expected_risks)
    severity_matches = sum(
        expected_risks[category].severity == identified_risks[category].severity
        for category in matched_risks
    )

    expected_controls = set(case.expected_controls)
    found_controls = set(output.recommended_controls)
    expected_governance = set(case.expected_governance_requirements)
    found_governance = set(output.governance_requirements)
    expected_architecture = set(case.expected_architecture_characteristics)
    found_architecture = set(output.architecture_characteristics)

    unsupported_claims: list[str] = []
    missing_citations: list[str] = []
    invalid_citations: list[str] = []
    requirements = {item.claim_id: item for item in case.evidence_requirements}
    available_specialist_findings = (
        set(output.specialists.available_finding_ids) if output.specialists is not None else set()
    )
    for claim in output.claims:
        requirement = requirements.get(claim.claim_id)
        if requirement is None:
            unsupported_claims.append(claim.claim_id)
            continue
        valid_support = any(
            _support_is_valid(item, requirement, available_specialist_findings)
            for item in claim.supports
        )
        if not valid_support:
            unsupported_claims.append(claim.claim_id)
        if requirement.citation_required:
            evidence_supports = [
                item
                for item in claim.supports
                if item.source == ClaimSupportSource.RETRIEVED_EVIDENCE
            ]
            if not evidence_supports:
                missing_citations.append(claim.claim_id)
            elif not any(
                item.reference_id in requirement.allowed_reference_ids for item in evidence_supports
            ):
                invalid_citations.append(claim.claim_id)

    claim_count = len(output.claims)
    supported_claim_count = claim_count - len(unsupported_claims)
    simple_expected = bool(
        {
            ArchitectureCharacteristic.DETERMINISTIC_SUFFICIENT,
            ArchitectureCharacteristic.SIMPLER_WORKFLOW_PREFERRED,
            ArchitectureCharacteristic.MULTI_AGENT_UNNECESSARY,
        }
        & expected_architecture
    )
    recommends_excessive_complexity = bool(
        {
            ArchitectureCharacteristic.AGENT_WORKFLOW_JUSTIFIED,
            ArchitectureCharacteristic.MULTI_AGENT_JUSTIFIED,
        }
        & found_architecture
    )

    specialist_preservation, synthesis_transparency = _evaluate_synthesis(output)
    observations = AssessmentQualityObservations(
        identified_risks=sorted(output.identified_risks, key=lambda item: item.category),
        missing_risks=sorted(set(expected_risks) - set(identified_risks), key=str),
        unexpected_risks=sorted(unexpected_risks, key=str),
        recommended_controls=sorted(found_controls, key=str),
        missing_controls=sorted(expected_controls - found_controls, key=str),
        governance_requirements=sorted(found_governance, key=str),
        missing_governance_requirements=sorted(expected_governance - found_governance, key=str),
        architecture_characteristics=sorted(found_architecture, key=str),
        missing_architecture_characteristics=sorted(
            expected_architecture - found_architecture, key=str
        ),
        unsupported_claim_ids=unsupported_claims,
        missing_citation_claim_ids=missing_citations,
        invalid_citation_claim_ids=invalid_citations,
        unacceptable_risks_identified=sorted(
            set(case.unacceptable_risks) & set(identified_risks), key=str
        ),
        human_oversight_expected=case.human_oversight_expected,
        human_oversight_recommended=output.human_oversight_recommended,
        abstention_expected=case.abstention.expectation,
        uncertainty_acknowledged=output.uncertainty_acknowledged,
        abstained_from_unsupported_conclusion=output.abstained_from_unsupported_conclusion,
        validation_recommended=output.validation_recommended,
        run_status=output.run_status,
        degradation_reasons=output.degradation_reasons,
    )
    metrics = AssessmentQualityMetrics(
        risk_recall=len(matched_risks) / len(expected_risks),
        risk_precision=(len(matched_risks) / len(identified_risks) if identified_risks else 0.0),
        severity_consistency=(severity_matches / len(matched_risks) if matched_risks else None),
        control_coverage=len(expected_controls & found_controls) / len(expected_controls),
        governance_coverage=(
            len(expected_governance & found_governance) / len(expected_governance)
        ),
        human_oversight_accuracy=float(
            output.human_oversight_recommended == case.human_oversight_expected
        ),
        architecture_fit_score=(
            len(expected_architecture & found_architecture) / len(expected_architecture)
        ),
        over_engineering_avoidance=(
            float(not recommends_excessive_complexity) if simple_expected else None
        ),
        groundedness=(supported_claim_count / claim_count if claim_count else None),
        unsupported_claim_rate=(len(unsupported_claims) / claim_count if claim_count else None),
        appropriate_abstention_rate=_abstention_score(case, output),
        specialist_preservation=specialist_preservation,
        synthesis_transparency=synthesis_transparency,
    )
    return metrics, observations


def aggregate_quality_metrics(
    metrics: Sequence[AssessmentQualityMetrics],
) -> AssessmentQualityMetrics:
    """Macro-average each supported metric independently."""
    names = AssessmentQualityMetrics.model_fields
    return AssessmentQualityMetrics(
        **{name: _average(getattr(item, name) for item in metrics) for name in names}
    )


def _support_is_valid(
    support: ClaimSupport,
    requirement: ExpectedEvidenceRequirement,
    available_specialist_findings: set[str],
) -> bool:
    if support.source not in requirement.allowed_sources:
        return False
    if support.source == ClaimSupportSource.ASSESSMENT_INPUT:
        return support.reference_id is None and support.system_knowledge_category is None
    if support.source == ClaimSupportSource.RETRIEVED_EVIDENCE:
        return support.reference_id in requirement.allowed_reference_ids
    if support.source == ClaimSupportSource.SPECIALIST_OUTPUT:
        return (
            support.reference_id in requirement.allowed_specialist_finding_ids
            and support.reference_id in available_specialist_findings
        )
    return support.system_knowledge_category in requirement.allowed_system_knowledge_categories


def _abstention_score(
    case: AssessmentEvaluationCase,
    output: AssessmentEvaluationOutput,
) -> float:
    expected = case.abstention
    if expected.expectation == AbstentionExpectation.REQUIRED:
        checks = [output.abstained_from_unsupported_conclusion]
        if expected.uncertainty_acknowledgment_required:
            checks.append(output.uncertainty_acknowledged)
        if expected.validation_recommendation_required:
            checks.append(output.validation_recommended)
        return sum(checks) / len(checks)
    return float(not output.abstained_from_unsupported_conclusion)


def _evaluate_synthesis(
    output: AssessmentEvaluationOutput,
) -> tuple[float | None, float | None]:
    specialists = output.specialists
    if specialists is None:
        return None, None
    important = set(specialists.important_finding_ids)
    preserved = set(output.preserved_specialist_finding_ids)
    preservation = len(important & preserved) / len(important) if important else None
    available = set(specialists.available_finding_ids)
    checks = [preserved.issubset(available)]
    if specialists.disagreement_ids:
        checks.append(set(specialists.disagreement_ids).issubset(output.surfaced_disagreement_ids))
    if specialists.unavailable_specialists or output.degradation_reasons:
        checks.append(output.degraded_state_acknowledged)
    return preservation, sum(checks) / len(checks)


def _average(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None
