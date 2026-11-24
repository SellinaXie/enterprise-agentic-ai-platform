"""Read-only, fingerprinted description of the runtime governance policy in force."""

import hashlib
import json

from app.runtime.models import (
    ReviewActionName,
    RuntimeReasonCode,
    RuntimeRiskDecision,
    RuntimeRiskLevel,
    RuntimeRiskPolicy,
)
from app.schemas.product import (
    GovernancePolicyResponse,
    PolicyFixedRule,
    SeparationOfDutiesPolicy,
)

SEPARATION_OF_DUTIES_ACTIONS: tuple[ReviewActionName, ...] = (
    ReviewActionName.APPROVE,
    ReviewActionName.REJECT,
    ReviewActionName.REQUEST_REVISION,
)

# Mirrors the unconditional branches of RuntimeRiskGate.evaluate.
FIXED_RULES: tuple[tuple[RuntimeReasonCode, RuntimeRiskDecision], ...] = (
    (RuntimeReasonCode.MODEL_FAILURE, RuntimeRiskDecision.BLOCK_AND_ESCALATE),
    (RuntimeReasonCode.MISSING_HUMAN_OVERSIGHT, RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW),
    (RuntimeReasonCode.UNSUPPORTED_CLAIM, RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW),
)


def describe_runtime_policy(
    policy: RuntimeRiskPolicy,
    *,
    runtime_risk_gate_enabled: bool,
    separation_of_duties_enforced: bool,
) -> GovernancePolicyResponse:
    """Project the configured policy into a stable public contract with a fingerprint."""
    body = {
        "runtime_risk_gate_enabled": runtime_risk_gate_enabled,
        "risk_level_decisions": {
            RuntimeRiskLevel.LOW: RuntimeRiskDecision.AUTO_COMPLETE,
            RuntimeRiskLevel.MEDIUM: policy.medium_risk_decision,
            RuntimeRiskLevel.HIGH: policy.high_risk_decision,
            RuntimeRiskLevel.CRITICAL: policy.critical_risk_decision,
        },
        "review_triggers": {
            "insufficient_evidence": policy.review_on_insufficient_evidence,
            "degraded_execution": policy.review_on_degraded_execution,
            "specialist_unavailable": policy.review_on_specialist_unavailable,
            "tool_failure": policy.review_on_tool_failure,
        },
        "block_rules": {
            "high_risk_invalid_provenance": policy.block_high_risk_invalid_provenance,
            "critical_missing_mitigation": policy.block_critical_missing_mitigation,
        },
        "fixed_rules": [
            PolicyFixedRule(signal=signal, decision=decision) for signal, decision in FIXED_RULES
        ],
        "max_human_revisions": policy.max_human_revisions,
        "separation_of_duties": SeparationOfDutiesPolicy(
            enforced=separation_of_duties_enforced,
            applies_to=list(SEPARATION_OF_DUTIES_ACTIONS),
        ),
        "reason_codes": list(RuntimeReasonCode),
    }
    unsigned = GovernancePolicyResponse(policy_fingerprint="sha256:pending", **body)
    canonical = json.dumps(
        unsigned.model_dump(mode="json", exclude={"policy_fingerprint"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return unsigned.model_copy(update={"policy_fingerprint": f"sha256:{digest}"})
