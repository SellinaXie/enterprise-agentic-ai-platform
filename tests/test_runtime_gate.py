"""Deterministic policy tests for the centralized V7C risk gate."""

import pytest

from app.runtime.gate import RuntimeRiskGate
from app.runtime.models import (
    QualityGateSignals,
    RuntimeReasonCode,
    RuntimeRiskDecision,
    RuntimeRiskLevel,
    RuntimeRiskPolicy,
)


@pytest.mark.parametrize(
    ("risk", "decision", "reason"),
    [
        (RuntimeRiskLevel.LOW, RuntimeRiskDecision.AUTO_COMPLETE, None),
        (
            RuntimeRiskLevel.MEDIUM,
            RuntimeRiskDecision.COMPLETE_WITH_WARNING,
            RuntimeReasonCode.MEDIUM_RISK,
        ),
        (
            RuntimeRiskLevel.HIGH,
            RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW,
            RuntimeReasonCode.HIGH_RISK,
        ),
        (
            RuntimeRiskLevel.CRITICAL,
            RuntimeRiskDecision.BLOCK_AND_ESCALATE,
            RuntimeReasonCode.CRITICAL_RISK,
        ),
    ],
)
def test_risk_levels_have_explicit_default_outcomes(
    risk: RuntimeRiskLevel,
    decision: RuntimeRiskDecision,
    reason: RuntimeReasonCode | None,
) -> None:
    result = RuntimeRiskGate(RuntimeRiskPolicy()).evaluate(QualityGateSignals(risk_level=risk))

    assert result.decision == decision
    assert (reason in result.reason_codes) if reason is not None else result.reason_codes == []


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        (
            {"evidence_required": True, "evidence_available": False},
            RuntimeReasonCode.INSUFFICIENT_EVIDENCE,
        ),
        ({"degraded_execution": True}, RuntimeReasonCode.DEGRADED_EXECUTION),
        ({"specialist_unavailable": True}, RuntimeReasonCode.SPECIALIST_UNAVAILABLE),
        ({"unsupported_claims_detected": True}, RuntimeReasonCode.UNSUPPORTED_CLAIM),
        ({"tool_failed": True}, RuntimeReasonCode.TOOL_FAILURE),
    ],
)
def test_quality_conditions_require_review(
    updates: dict[str, bool], reason: RuntimeReasonCode
) -> None:
    signals = QualityGateSignals(risk_level=RuntimeRiskLevel.LOW).model_copy(update=updates)

    result = RuntimeRiskGate(RuntimeRiskPolicy()).evaluate(signals)

    assert result.decision == RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW
    assert reason in result.reason_codes


def test_high_risk_invalid_provenance_blocks() -> None:
    result = RuntimeRiskGate(RuntimeRiskPolicy()).evaluate(
        QualityGateSignals(
            risk_level=RuntimeRiskLevel.HIGH,
            provenance_valid=False,
        )
    )

    assert result.blocked is True
    assert RuntimeReasonCode.INVALID_PROVENANCE in result.reason_codes


def test_critical_missing_mitigation_blocks() -> None:
    result = RuntimeRiskGate(RuntimeRiskPolicy()).evaluate(
        QualityGateSignals(
            risk_level=RuntimeRiskLevel.CRITICAL,
            mitigations_complete=False,
        )
    )

    assert result.decision == RuntimeRiskDecision.BLOCK_AND_ESCALATE
    assert RuntimeReasonCode.MISSING_RISK_MITIGATION in result.reason_codes


def test_policy_thresholds_are_configurable() -> None:
    policy = RuntimeRiskPolicy(
        medium_risk_decision=RuntimeRiskDecision.AUTO_COMPLETE,
        high_risk_decision=RuntimeRiskDecision.COMPLETE_WITH_WARNING,
        review_on_insufficient_evidence=False,
    )

    result = RuntimeRiskGate(policy).evaluate(
        QualityGateSignals(
            risk_level=RuntimeRiskLevel.HIGH,
            evidence_required=True,
            evidence_available=False,
        )
    )

    assert result.decision == RuntimeRiskDecision.COMPLETE_WITH_WARNING
    assert RuntimeReasonCode.INSUFFICIENT_EVIDENCE in result.reason_codes


def test_model_failure_always_blocks() -> None:
    result = RuntimeRiskGate(RuntimeRiskPolicy()).evaluate(
        QualityGateSignals(risk_level=RuntimeRiskLevel.LOW, model_failed=True)
    )

    assert result.decision == RuntimeRiskDecision.BLOCK_AND_ESCALATE
    assert RuntimeReasonCode.MODEL_FAILURE in result.reason_codes
