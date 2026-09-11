"""Central deterministic runtime risk and quality gate."""

from app.runtime.models import (
    QualityGateResult,
    QualityGateSignals,
    RuntimeReasonCode,
    RuntimeRiskDecision,
    RuntimeRiskLevel,
    RuntimeRiskPolicy,
)


class RuntimeRiskGate:
    """Apply one configurable policy after assessment validation and synthesis."""

    def __init__(self, policy: RuntimeRiskPolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> RuntimeRiskPolicy:
        return self._policy

    def evaluate(self, signals: QualityGateSignals) -> QualityGateResult:
        """Return the strongest justified outcome and every contributing reason."""
        reasons = _reason_codes(signals)
        decision = _risk_decision(signals.risk_level, self._policy)

        if signals.model_failed:
            decision = RuntimeRiskDecision.BLOCK_AND_ESCALATE
        if (
            not signals.provenance_valid
            and self._policy.block_high_risk_invalid_provenance
            and signals.risk_level in {RuntimeRiskLevel.HIGH, RuntimeRiskLevel.CRITICAL}
        ):
            decision = RuntimeRiskDecision.BLOCK_AND_ESCALATE
        if (
            not signals.mitigations_complete
            and self._policy.block_critical_missing_mitigation
            and signals.risk_level == RuntimeRiskLevel.CRITICAL
        ):
            decision = RuntimeRiskDecision.BLOCK_AND_ESCALATE

        review_conditions = (
            signals.evidence_required
            and not signals.evidence_available
            and self._policy.review_on_insufficient_evidence,
            signals.degraded_execution and self._policy.review_on_degraded_execution,
            signals.specialist_unavailable and self._policy.review_on_specialist_unavailable,
            signals.tool_failed and self._policy.review_on_tool_failure,
            signals.retrieval_failed and self._policy.review_on_insufficient_evidence,
            signals.human_oversight_required and not signals.human_oversight_present,
            signals.unsupported_claims_detected,
        )
        if any(review_conditions) and _priority(decision) < _priority(
            RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW
        ):
            decision = RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW

        return QualityGateResult(
            decision=decision,
            risk_level=signals.risk_level,
            reason_codes=reasons,
            review_required=decision == RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW,
            blocked=decision == RuntimeRiskDecision.BLOCK_AND_ESCALATE,
        )


def _risk_decision(
    risk_level: RuntimeRiskLevel,
    policy: RuntimeRiskPolicy,
) -> RuntimeRiskDecision:
    if risk_level == RuntimeRiskLevel.CRITICAL:
        return policy.critical_risk_decision
    if risk_level == RuntimeRiskLevel.HIGH:
        return policy.high_risk_decision
    if risk_level == RuntimeRiskLevel.MEDIUM:
        return policy.medium_risk_decision
    return RuntimeRiskDecision.AUTO_COMPLETE


def _reason_codes(signals: QualityGateSignals) -> list[RuntimeReasonCode]:
    reasons: list[RuntimeReasonCode] = []
    if signals.risk_level == RuntimeRiskLevel.MEDIUM:
        reasons.append(RuntimeReasonCode.MEDIUM_RISK)
    elif signals.risk_level == RuntimeRiskLevel.HIGH:
        reasons.append(RuntimeReasonCode.HIGH_RISK)
    elif signals.risk_level == RuntimeRiskLevel.CRITICAL:
        reasons.append(RuntimeReasonCode.CRITICAL_RISK)
    if signals.evidence_required and not signals.evidence_available:
        reasons.append(RuntimeReasonCode.INSUFFICIENT_EVIDENCE)
    if not signals.provenance_valid:
        reasons.append(RuntimeReasonCode.INVALID_PROVENANCE)
    if signals.degraded_execution:
        reasons.append(RuntimeReasonCode.DEGRADED_EXECUTION)
    if signals.specialist_unavailable:
        reasons.append(RuntimeReasonCode.SPECIALIST_UNAVAILABLE)
    if signals.human_oversight_required and not signals.human_oversight_present:
        reasons.append(RuntimeReasonCode.MISSING_HUMAN_OVERSIGHT)
    if not signals.mitigations_complete:
        reasons.append(RuntimeReasonCode.MISSING_RISK_MITIGATION)
    if signals.unsupported_claims_detected:
        reasons.append(RuntimeReasonCode.UNSUPPORTED_CLAIM)
    if signals.model_failed:
        reasons.append(RuntimeReasonCode.MODEL_FAILURE)
    if signals.tool_failed:
        reasons.append(RuntimeReasonCode.TOOL_FAILURE)
    if signals.retrieval_failed:
        reasons.append(RuntimeReasonCode.RETRIEVAL_FAILURE)
    return reasons


def _priority(decision: RuntimeRiskDecision) -> int:
    return {
        RuntimeRiskDecision.AUTO_COMPLETE: 0,
        RuntimeRiskDecision.COMPLETE_WITH_WARNING: 1,
        RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW: 2,
        RuntimeRiskDecision.BLOCK_AND_ESCALATE: 3,
    }[decision]
