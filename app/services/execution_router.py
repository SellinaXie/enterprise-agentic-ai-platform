"""Deterministic per-request selection of an existing assessment workflow."""

import re
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assessment import AssessmentRequest


class ExecutionMode(StrEnum):
    """Supported assessment execution paths."""

    DETERMINISTIC = "deterministic"
    SINGLE_AGENT = "single_agent"
    MULTI_AGENT = "multi_agent"


class RoutingReasonCode(StrEnum):
    """Public-safe explanations for deterministic routing decisions."""

    ENVIRONMENT_OVERRIDE = "environment_override"
    BOUNDED_SCOPE = "bounded_scope"
    LOW_COORDINATION_COMPLEXITY = "low_coordination_complexity"
    MULTIPLE_PAIN_POINTS = "multiple_pain_points"
    MULTIPLE_CONSTRAINTS = "multiple_constraints"
    MULTIPLE_WORKLOAD_CONCERNS = "multiple_workload_concerns"
    RICH_PROCESS_CONTEXT = "rich_process_context"
    SINGLE_REASONING_CONTEXT_SUFFICIENT = "single_reasoning_context_sufficient"
    CROSS_FUNCTIONAL_COORDINATION = "cross_functional_coordination"
    SPECIALIST_SEPARATION_BENEFICIAL = "specialist_separation_beneficial"
    LEGACY_FLAG_SELECTION = "legacy_flag_selection"


class FallbackReasonCode(StrEnum):
    """Public-safe reasons why execution differed from the preferred route."""

    MULTI_AGENT_CAPABILITY_UNAVAILABLE = "multi_agent_capability_unavailable"
    SINGLE_AGENT_CAPABILITY_UNAVAILABLE = "single_agent_capability_unavailable"
    FALLBACK_TO_SINGLE_AGENT = "fallback_to_single_agent"
    FALLBACK_TO_DETERMINISTIC = "fallback_to_deterministic"


class ExecutionRoutingDecision(BaseModel):
    """One explainable preferred workflow selection without private reasoning."""

    model_config = ConfigDict(extra="forbid")

    preferred_execution_mode: ExecutionMode
    reason_codes: list[RoutingReasonCode] = Field(min_length=1, max_length=12)


class ResolvedExecutionRoute(BaseModel):
    """Preferred and executable modes after capability-aware fallback."""

    model_config = ConfigDict(extra="forbid")

    preferred_execution_mode: ExecutionMode
    execution_mode: ExecutionMode
    routing_reason_codes: list[RoutingReasonCode] = Field(default_factory=list, max_length=12)
    fallback_reason_codes: list[FallbackReasonCode] = Field(default_factory=list, max_length=12)


class ExecutionRouter:
    """Choose an execution path from bounded workload-complexity signals."""

    MULTIPLE_PAIN_POINTS_THRESHOLD = 2
    MULTIPLE_CONSTRAINTS_THRESHOLD = 2
    SPECIALIST_CONCERNS_THRESHOLD = 3

    _CONCERN_KEYWORDS: dict[str, tuple[str, ...]] = {
        "data": (
            "data",
            "record",
            "records",
            "document",
            "documents",
            "information quality",
        ),
        "integration": (
            "integration",
            "integrations",
            "integrate",
            "api",
            "apis",
            "system",
            "systems",
            "handoff",
            "handoffs",
        ),
        "security_privacy": (
            "security",
            "privacy",
            "confidential",
            "sensitive",
            "access control",
            "permission",
        ),
        "governance_risk": (
            "risk",
            "compliance",
            "audit",
            "policy",
            "regulatory",
            "approval",
            "oversight",
        ),
        "operations": (
            "operations",
            "reliability",
            "monitoring",
            "latency",
            "scalability",
            "deployment",
        ),
        "people_change": (
            "team",
            "department",
            "stakeholder",
            "training",
            "change management",
            "customer",
            "employee",
        ),
    }
    _COORDINATION_KEYWORDS = (
        "cross-functional",
        "cross functional",
        "multiple teams",
        "multiple departments",
        "across teams",
        "across departments",
        "across systems",
        "end-to-end",
        "end to end",
        "multiple stakeholders",
        "parallel workstreams",
    )

    def __init__(
        self,
        *,
        forced_mode: Literal["deterministic", "single_agent", "multi_agent"] | None = None,
    ) -> None:
        self._forced_mode = ExecutionMode(forced_mode) if forced_mode is not None else None

    def route(self, request: AssessmentRequest) -> ExecutionRoutingDecision:
        """Return one deterministic decision derived only from request workload fields."""
        if self._forced_mode is not None:
            return ExecutionRoutingDecision(
                preferred_execution_mode=self._forced_mode,
                reason_codes=[RoutingReasonCode.ENVIRONMENT_OVERRIDE],
            )

        text = self._workload_text(request)
        concern_count = sum(
            any(self._contains_term(text, keyword) for keyword in keywords)
            for keywords in self._CONCERN_KEYWORDS.values()
        )
        has_coordination_signal = any(
            self._contains_term(text, keyword) for keyword in self._COORDINATION_KEYWORDS
        )
        multiple_pain_points = len(request.pain_points) >= self.MULTIPLE_PAIN_POINTS_THRESHOLD
        multiple_constraints = len(request.constraints) >= self.MULTIPLE_CONSTRAINTS_THRESHOLD
        rich_process_context = bool(request.current_process and request.additional_context)

        reasons: list[RoutingReasonCode] = []
        if multiple_pain_points:
            reasons.append(RoutingReasonCode.MULTIPLE_PAIN_POINTS)
        if multiple_constraints:
            reasons.append(RoutingReasonCode.MULTIPLE_CONSTRAINTS)
        if concern_count >= 2:
            reasons.append(RoutingReasonCode.MULTIPLE_WORKLOAD_CONCERNS)
        if rich_process_context:
            reasons.append(RoutingReasonCode.RICH_PROCESS_CONTEXT)

        specialist_separation_is_useful = concern_count >= self.SPECIALIST_CONCERNS_THRESHOLD and (
            has_coordination_signal
            or len(request.pain_points) >= 3
            or len(request.constraints) >= 3
        )
        if specialist_separation_is_useful:
            if has_coordination_signal:
                reasons.append(RoutingReasonCode.CROSS_FUNCTIONAL_COORDINATION)
            reasons.append(RoutingReasonCode.SPECIALIST_SEPARATION_BENEFICIAL)
            return ExecutionRoutingDecision(
                preferred_execution_mode=ExecutionMode.MULTI_AGENT,
                reason_codes=reasons,
            )

        if reasons:
            reasons.append(RoutingReasonCode.SINGLE_REASONING_CONTEXT_SUFFICIENT)
            return ExecutionRoutingDecision(
                preferred_execution_mode=ExecutionMode.SINGLE_AGENT,
                reason_codes=reasons,
            )

        return ExecutionRoutingDecision(
            preferred_execution_mode=ExecutionMode.DETERMINISTIC,
            reason_codes=[
                RoutingReasonCode.BOUNDED_SCOPE,
                RoutingReasonCode.LOW_COORDINATION_COMPLEXITY,
            ],
        )

    @staticmethod
    def _workload_text(request: AssessmentRequest) -> str:
        values = [
            request.business_problem,
            request.desired_outcome,
            request.current_process or "",
            *request.pain_points,
            *request.constraints,
            request.additional_context or "",
        ]
        return " ".join(values).casefold()

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None
