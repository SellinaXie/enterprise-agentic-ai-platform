"""LangGraph nodes for controlled V5 specialist orchestration."""

import logging
from datetime import UTC, datetime
from time import perf_counter

from app.agents.architecture_agent import ArchitectureAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.multi_agent_models import (
    EvidenceBrief,
    MultiAgentDurations,
    MultiAgentErrors,
    MultiAgentExecutionMetadata,
    MultiAgentName,
    MultiAgentStatus,
    MultiAgentStatuses,
    MultiAgentTerminationReason,
    MultiAgentTraceEvent,
    MultiAgentTraceEventType,
)
from app.agents.risk_governance_agent import RiskGovernanceAgent
from app.agents.synthesis_agent import SynthesisAgent
from app.core.exceptions import ApplicationError, AssessmentGenerationError
from app.graph.multi_agent_state import MultiAgentGraphState
from app.schemas.assessment import AssessmentResult

logger = logging.getLogger(__name__)


def _event(
    *,
    event_type: MultiAgentTraceEventType,
    summary: str,
    agent: MultiAgentName | None = None,
    tool_name: str | None = None,
    error_code: str | None = None,
) -> MultiAgentTraceEvent:
    return MultiAgentTraceEvent(
        sequence=0,
        timestamp=datetime.now(UTC),
        agent=agent,
        event_type=event_type,
        summary=summary,
        tool_name=tool_name,
        error_code=error_code,
    )


def _safe_error_code(exc: Exception) -> str:
    return exc.error_code if isinstance(exc, ApplicationError) else "specialist_generation_failed"


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1_000))


class MultiAgentGraphNodes:
    """Bind exactly four specialist contracts to explicit orchestration nodes."""

    def __init__(
        self,
        *,
        evidence: EvidenceAgent,
        architecture: ArchitectureAgent,
        risk_governance: RiskGovernanceAgent,
        synthesis: SynthesisAgent,
    ) -> None:
        self._evidence = evidence
        self._architecture = architecture
        self._risk_governance = risk_governance
        self._synthesis = synthesis

    def initialize(self, state: MultiAgentGraphState) -> dict[str, object]:
        """Start one workflow without invoking a free-form supervisor."""
        logger.info("multi_agent_workflow_started", extra={"assessment_id": state["assessment_id"]})
        return {
            "started_at": datetime.now(UTC),
            "initialization_trace": [
                _event(
                    event_type=MultiAgentTraceEventType.WORKFLOW_STARTED,
                    summary="The controlled four-agent workflow started.",
                )
            ],
        }

    def evidence(self, state: MultiAgentGraphState) -> dict[str, object]:
        """Run the only tool-capable specialist and degrade safely on failure."""
        started = perf_counter()
        trace = [
            _event(
                agent=MultiAgentName.EVIDENCE,
                event_type=MultiAgentTraceEventType.AGENT_STARTED,
                summary="Evidence analysis started with approved read-only tools.",
            )
        ]
        try:
            outcome = self._evidence.gather(state["request"])
        except Exception as exc:
            error_code = _safe_error_code(exc)
            logger.warning(
                "multi_agent_specialist_failed",
                extra={
                    "assessment_id": state["assessment_id"],
                    "agent": MultiAgentName.EVIDENCE.value,
                    "error_code": error_code,
                },
            )
            trace.extend(
                [
                    _event(
                        agent=MultiAgentName.EVIDENCE,
                        event_type=MultiAgentTraceEventType.AGENT_FAILED,
                        summary="Evidence analysis did not complete.",
                        error_code=error_code,
                    ),
                    _event(
                        event_type=MultiAgentTraceEventType.DEGRADED_MODE,
                        summary="The workflow continued with assessment-only evidence context.",
                    ),
                ]
            )
            return {
                "evidence_brief": EvidenceBrief.unavailable(),
                "evidence_status": MultiAgentStatus.FAILED,
                "evidence_error": error_code,
                "evidence_duration_ms": _elapsed_ms(started),
                "evidence_trace": trace,
            }

        for item in outcome.tool_history:
            if item.error_code == "unauthorized_tool":
                event_type = MultiAgentTraceEventType.TOOL_AUTHORIZATION_DENIED
            elif item.success:
                event_type = MultiAgentTraceEventType.TOOL_COMPLETED
            else:
                event_type = MultiAgentTraceEventType.TOOL_FAILED
            trace.append(
                _event(
                    agent=MultiAgentName.EVIDENCE,
                    event_type=event_type,
                    summary=item.summary,
                    tool_name=item.tool_name,
                    error_code=item.error_code,
                )
            )
        trace.append(
            _event(
                agent=MultiAgentName.EVIDENCE,
                event_type=MultiAgentTraceEventType.AGENT_COMPLETED,
                summary="The Evidence Agent produced a typed EvidenceBrief.",
            )
        )
        return {
            "evidence_brief": outcome.brief,
            "retrieved_evidence": list(outcome.evidence),
            "observed_documents": list(outcome.documents),
            "tool_history": list(outcome.tool_history),
            "evidence_steps_used": outcome.steps_used,
            "evidence_termination_reason": outcome.termination_reason,
            "graph_retrieval": outcome.graph_retrieval,
            "evidence_status": MultiAgentStatus.COMPLETED,
            "evidence_duration_ms": _elapsed_ms(started),
            "evidence_trace": trace,
        }

    def architecture(self, state: MultiAgentGraphState) -> dict[str, object]:
        """Analyze architecture in one parallel branch with no tools."""
        started = perf_counter()
        trace = [
            _event(
                agent=MultiAgentName.ARCHITECTURE,
                event_type=MultiAgentTraceEventType.AGENT_STARTED,
                summary="Independent solution architecture analysis started.",
            )
        ]
        try:
            brief = state["evidence_brief"] or EvidenceBrief.unavailable()
            result = self._architecture.analyze(state["request"], brief)
        except Exception as exc:
            error_code = _safe_error_code(exc)
            logger.warning(
                "multi_agent_specialist_failed",
                extra={
                    "assessment_id": state["assessment_id"],
                    "agent": MultiAgentName.ARCHITECTURE.value,
                    "error_code": error_code,
                },
            )
            trace.append(
                _event(
                    agent=MultiAgentName.ARCHITECTURE,
                    event_type=MultiAgentTraceEventType.AGENT_FAILED,
                    summary="Solution architecture analysis did not complete.",
                    error_code=error_code,
                )
            )
            return {
                "architecture_status": MultiAgentStatus.FAILED,
                "architecture_error": error_code,
                "architecture_duration_ms": _elapsed_ms(started),
                "architecture_trace": trace,
            }
        trace.append(
            _event(
                agent=MultiAgentName.ARCHITECTURE,
                event_type=MultiAgentTraceEventType.AGENT_COMPLETED,
                summary="The Architecture Agent produced a typed recommendation.",
            )
        )
        return {
            "architecture_recommendation": result,
            "architecture_status": MultiAgentStatus.COMPLETED,
            "architecture_duration_ms": _elapsed_ms(started),
            "architecture_trace": trace,
        }

    def risk_governance(self, state: MultiAgentGraphState) -> dict[str, object]:
        """Analyze controls independently in the other parallel branch with no tools."""
        started = perf_counter()
        trace = [
            _event(
                agent=MultiAgentName.RISK_GOVERNANCE,
                event_type=MultiAgentTraceEventType.AGENT_STARTED,
                summary="Independent risk and governance analysis started.",
            )
        ]
        try:
            brief = state["evidence_brief"] or EvidenceBrief.unavailable()
            result = self._risk_governance.review(state["request"], brief)
        except Exception as exc:
            error_code = _safe_error_code(exc)
            logger.warning(
                "multi_agent_specialist_failed",
                extra={
                    "assessment_id": state["assessment_id"],
                    "agent": MultiAgentName.RISK_GOVERNANCE.value,
                    "error_code": error_code,
                },
            )
            trace.append(
                _event(
                    agent=MultiAgentName.RISK_GOVERNANCE,
                    event_type=MultiAgentTraceEventType.AGENT_FAILED,
                    summary="Risk and governance analysis did not complete.",
                    error_code=error_code,
                )
            )
            return {
                "risk_governance_status": MultiAgentStatus.FAILED,
                "risk_governance_error": error_code,
                "risk_governance_duration_ms": _elapsed_ms(started),
                "risk_governance_trace": trace,
            }
        trace.append(
            _event(
                agent=MultiAgentName.RISK_GOVERNANCE,
                event_type=MultiAgentTraceEventType.AGENT_COMPLETED,
                summary="The Risk & Governance Agent produced a typed review.",
            )
        )
        return {
            "risk_governance_review": result,
            "risk_governance_status": MultiAgentStatus.COMPLETED,
            "risk_governance_duration_ms": _elapsed_ms(started),
            "risk_governance_trace": trace,
        }

    def synthesize(self, state: MultiAgentGraphState) -> dict[str, object]:
        """Fan in both branches and require a final schema-valid synthesis."""
        failures = sum(
            value is not None
            for value in (
                state["evidence_error"],
                state["architecture_error"],
                state["risk_governance_error"],
            )
        )
        available = (
            state["evidence_status"] == MultiAgentStatus.COMPLETED
            or state["architecture_recommendation"] is not None
            or state["risk_governance_review"] is not None
        )
        if failures > state["max_failures"] or not available:
            raise AssessmentGenerationError

        reasons = _degradation_reasons(state)
        started = perf_counter()
        trace = [
            _event(
                agent=MultiAgentName.SYNTHESIS,
                event_type=MultiAgentTraceEventType.AGENT_STARTED,
                summary="Typed specialist outputs converged for final synthesis.",
            )
        ]
        result = self._synthesis.synthesize(
            request=state["request"],
            evidence_brief=state["evidence_brief"] or EvidenceBrief.unavailable(),
            architecture=state["architecture_recommendation"],
            risk_governance=state["risk_governance_review"],
            degradation_reasons=reasons,
        )
        if reasons:
            limitations = [f"Specialist limitation: {reason}" for reason in reasons]
            result = result.model_copy(
                update={"information_gaps": [*result.information_gaps, *limitations]}
            )
        trace.append(
            _event(
                agent=MultiAgentName.SYNTHESIS,
                event_type=MultiAgentTraceEventType.AGENT_COMPLETED,
                summary="The Synthesis Agent produced the existing AssessmentResult contract.",
            )
        )
        return {
            "final_result": result,
            "synthesis_status": MultiAgentStatus.COMPLETED,
            "synthesis_duration_ms": _elapsed_ms(started),
            "synthesis_trace": trace,
        }

    def validate(self, state: MultiAgentGraphState) -> dict[str, object]:
        """Validate convergence and build safe metadata in a fixed branch order."""
        if state["final_result"] is None:
            raise AssessmentGenerationError
        result = AssessmentResult.model_validate(state["final_result"])
        reasons = _degradation_reasons(state)
        trace = [
            *state["initialization_trace"],
            *state["evidence_trace"],
            *state["architecture_trace"],
            *state["risk_governance_trace"],
            *state["synthesis_trace"],
            _event(
                event_type=MultiAgentTraceEventType.WORKFLOW_COMPLETED,
                summary=(
                    "The multi-agent workflow completed in degraded mode."
                    if reasons
                    else "The multi-agent workflow completed with all specialists."
                ),
            ),
        ]
        trace = [event.model_copy(update={"sequence": index}) for index, event in enumerate(trace)]
        tools_used = list(dict.fromkeys(item.tool_name for item in state["tool_history"]))
        execution = MultiAgentExecutionMetadata(
            agent_statuses=MultiAgentStatuses(
                evidence=state["evidence_status"],
                architecture=state["architecture_status"],
                risk_governance=state["risk_governance_status"],
                synthesis=state["synthesis_status"],
            ),
            agent_durations_ms=MultiAgentDurations(
                evidence=state["evidence_duration_ms"],
                architecture=state["architecture_duration_ms"],
                risk_governance=state["risk_governance_duration_ms"],
                synthesis=state["synthesis_duration_ms"],
            ),
            agent_errors=MultiAgentErrors(
                evidence=state["evidence_error"],
                architecture=state["architecture_error"],
                risk_governance=state["risk_governance_error"],
                synthesis=state["synthesis_error"],
            ),
            tools_used=tools_used,
            tool_calls=len(state["tool_history"]),
            degraded_mode=bool(reasons),
            degradation_reasons=reasons,
            termination_reason=(
                MultiAgentTerminationReason.COMPLETED_DEGRADED
                if reasons
                else MultiAgentTerminationReason.COMPLETED
            ),
            trace=trace,
            graph_retrieval=state["graph_retrieval"],
        )
        return {
            "final_result": result,
            "execution": execution,
            "completed_at": datetime.now(UTC),
            "validation_trace": trace[-1:],
        }


def _degradation_reasons(state: MultiAgentGraphState) -> list[str]:
    reasons = []
    if state["evidence_error"] is not None:
        reasons.append("Evidence Agent output unavailable; assessment-only context used.")
    if state["architecture_error"] is not None:
        reasons.append("Architecture Agent output unavailable.")
    if state["risk_governance_error"] is not None:
        reasons.append("Risk & Governance Agent output unavailable; governance confidence reduced.")
    return reasons
