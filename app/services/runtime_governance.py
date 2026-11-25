"""Central post-generation governance and durable human-review workflow."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import ValidationError

from app.agents.models import (
    AgentTraceEventType,
    AssessmentExecutionMetadata,
    DeterministicExecutionMetadata,
)
from app.agents.multi_agent_models import (
    MultiAgentExecutionMetadata,
    MultiAgentStatus,
    MultiAgentTraceEventType,
)
from app.core.context import get_request_id
from app.core.exceptions import (
    AssessmentNotFoundError,
    InvalidReviewTransitionError,
    PersistenceError,
    RevisionLimitReachedError,
    RuntimeStateNotFoundError,
    SelfReviewForbiddenError,
)
from app.identity.models import AuthenticatedPrincipal
from app.models.assessment import AssessmentStatus, RiskSeverity
from app.models.knowledge import RetrievedEvidence
from app.models.persisted_assessment import PersistedAssessment
from app.observability.exporters import NoOpTelemetryExporter, OperationalTelemetryExporter
from app.repositories.runtime_reviews import RuntimeReviewRepository
from app.runtime.gate import RuntimeRiskGate
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import (
    CandidateVersionFeedback,
    ExecutionHealth,
    HumanReviewAction,
    HumanReviewDecision,
    HumanReviewRecord,
    HumanReviewRequest,
    HumanReviewStatus,
    OperationalTelemetry,
    QualityGateResult,
    QualityGateSignals,
    ReviewActionName,
    RuntimeAssessmentState,
    RuntimeRiskDecision,
    RuntimeRiskLevel,
    RuntimeStatusResponse,
    RuntimeTraceEvent,
    RuntimeTraceEventType,
)
from app.runtime.policy import SEPARATION_OF_DUTIES_ACTIONS
from app.runtime.telemetry import build_operational_telemetry
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.schemas.decision_record import (
    DecisionRecordCandidateVersion,
    DecisionRecordInput,
    DecisionRecordOutcome,
    DecisionRecordResponse,
    DecisionRecordReview,
    routing_from_execution,
)
from app.schemas.product import (
    CandidateVersionItem,
    CandidateVersionsResponse,
    DeniedReviewAction,
    ReviewCandidateResponse,
)

logger = logging.getLogger(__name__)


class AssessmentLifecycleRepository(Protocol):
    """Assessment mutations used by runtime governance."""

    def get_by_id(self, assessment_id: UUID) -> PersistedAssessment | None: ...

    def mark_completed(
        self,
        assessment_id: UUID,
        result_payload: dict[str, Any],
        execution_metadata: dict[str, Any] | None = None,
    ) -> PersistedAssessment | None: ...

    def mark_pending_review(
        self,
        assessment_id: UUID,
        execution_metadata: dict[str, Any] | None = None,
    ) -> PersistedAssessment | None: ...

    def mark_failed(
        self,
        assessment_id: UUID,
        *,
        error_code: str,
        error_message: str,
    ) -> PersistedAssessment | None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


ExecutionMetadata = (
    DeterministicExecutionMetadata | AssessmentExecutionMetadata | MultiAgentExecutionMetadata
)


class RuntimeGovernanceService:
    """Gate validated candidates and safely resume persisted review checkpoints."""

    def __init__(
        self,
        *,
        assessments: AssessmentLifecycleRepository,
        reviews: RuntimeReviewRepository,
        gate: RuntimeRiskGate,
        input_cost_per_million: float | None = None,
        output_cost_per_million: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        telemetry_exporter: OperationalTelemetryExporter | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        enforce_separation_of_duties: bool = False,
        policy_fingerprint: str | None = None,
    ) -> None:
        self._assessments = assessments
        self._reviews = reviews
        self._gate = gate
        self._input_cost_per_million = input_cost_per_million
        self._output_cost_per_million = output_cost_per_million
        self._metrics = metrics
        self._telemetry_exporter = telemetry_exporter or NoOpTelemetryExporter()
        self._clock = clock
        self._enforce_separation_of_duties = enforce_separation_of_duties
        self._policy_fingerprint = policy_fingerprint

    def process_candidate(
        self,
        *,
        assessment_id: UUID,
        result: AssessmentResult,
        evidence: tuple[RetrievedEvidence, ...],
        execution: ExecutionMetadata,
        duration_ms: int,
        provenance_valid: bool = True,
        retrieval_duration_ms: int | None = None,
        signal_overrides: dict[str, bool | RuntimeRiskLevel] | None = None,
        revision_count: int = 0,
        record_review_request: bool = True,
        feedback_review_id: UUID | None = None,
    ) -> PersistedAssessment:
        """Persist one centralized gate decision and return the lifecycle record."""
        signals = self.derive_signals(
            result=result,
            evidence=evidence,
            execution=execution,
            provenance_valid=provenance_valid,
        )
        if signal_overrides:
            signals = signals.model_copy(update=signal_overrides)
        gate_result = self._gate.evaluate(signals)
        telemetry = build_operational_telemetry(
            execution=execution,
            duration_ms=duration_ms,
            gate_decision=gate_result.decision,
            evidence_count=len(evidence),
            model_call_count=(
                len(self._metrics.model_call_durations_ms) if self._metrics is not None else None
            ),
            token_usage=self._metrics.token_usage if self._metrics is not None else None,
            input_cost_per_million=self._input_cost_per_million,
            output_cost_per_million=self._output_cost_per_million,
            request_id=get_request_id(),
            now=self._clock(),
        )
        if self._metrics is not None:
            observed_retrieval_ms = retrieval_duration_ms
            if observed_retrieval_ms is None and self._metrics.tool_call_durations_ms:
                observed_retrieval_ms = sum(self._metrics.tool_call_durations_ms)
            synthesis_duration_ms = telemetry.synthesis_duration_ms
            if synthesis_duration_ms is None and self._metrics.model_call_durations_ms:
                synthesis_duration_ms = self._metrics.model_call_durations_ms[-1]
            telemetry = telemetry.model_copy(
                update={
                    "model_call_durations_ms": self._metrics.model_call_durations_ms,
                    "embedding_call_count": len(self._metrics.embedding_call_durations_ms),
                    "retrieval_duration_ms": observed_retrieval_ms,
                    "synthesis_duration_ms": synthesis_duration_ms,
                    "retry_count": self._metrics.retry_count,
                    "timeout_count": self._metrics.timeout_count,
                }
            )
        result_payload = result.model_dump(mode="json")
        execution_payload = execution.model_dump(mode="json")
        review_status = HumanReviewStatus.NOT_REQUIRED

        if gate_result.decision == RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW:
            review_status = HumanReviewStatus.PENDING
            record = self._assessments.mark_pending_review(assessment_id, execution_payload)
            telemetry = self._append_event(
                telemetry,
                RuntimeTraceEventType.HUMAN_REVIEW_REQUESTED,
                HumanReviewStatus.PENDING.value,
            )
        elif gate_result.decision == RuntimeRiskDecision.BLOCK_AND_ESCALATE:
            record = self._assessments.mark_failed(
                assessment_id,
                error_code="runtime_risk_gate_blocked",
                error_message="The assessment was blocked by the runtime risk and quality gate.",
            )
            telemetry = self._append_event(
                telemetry,
                RuntimeTraceEventType.ASSESSMENT_FAILED,
                "blocked",
                component="assessment",
            )
        else:
            record = self._assessments.mark_completed(
                assessment_id, result_payload, execution_payload
            )
            telemetry = self._append_event(
                telemetry,
                RuntimeTraceEventType.ASSESSMENT_COMPLETED,
                gate_result.decision.value,
                component="assessment",
            )

        if record is None:
            raise PersistenceError
        self._reviews.save_state(
            assessment_id=assessment_id,
            gate_result=gate_result,
            review_status=review_status,
            candidate_result=result_payload,
            candidate_execution=execution_payload,
            telemetry=telemetry,
            revision_count=revision_count,
            max_revisions=self._gate.policy.max_human_revisions,
        )
        self._reviews.add_candidate_version(
            assessment_id=assessment_id,
            version_number=revision_count,
            result=result_payload,
            execution=execution_payload,
            gate_result=gate_result,
            feedback_review_id=feedback_review_id,
            policy_fingerprint=self._policy_fingerprint,
        )
        if review_status == HumanReviewStatus.PENDING and record_review_request:
            self._reviews.add_review_event(
                assessment_id=assessment_id,
                action=HumanReviewAction.REQUESTED,
                previous_status=HumanReviewStatus.NOT_REQUIRED,
                new_status=HumanReviewStatus.PENDING,
                reviewer_id=None,
                comment=None,
                reason_codes=gate_result.reason_codes,
                revision_number=revision_count,
            )
        self._export_telemetry(assessment_id, telemetry, gate_result)
        return record

    def get_runtime_status(self, assessment_id: UUID) -> RuntimeStatusResponse:
        state = self._required_state(assessment_id)
        return RuntimeStatusResponse(
            assessment_id=assessment_id,
            gate_result=state.gate_result,
            review_status=state.review_status,
            revision_count=state.revision_count,
            max_revisions=state.max_revisions,
            telemetry=state.telemetry,
        )

    def list_reviews(self, assessment_id: UUID) -> list[HumanReviewRecord]:
        self._required_assessment(assessment_id)
        return self._reviews.list_review_events(assessment_id)

    def get_review_candidate(
        self,
        assessment_id: UUID,
        *,
        principal: AuthenticatedPrincipal | None = None,
    ) -> ReviewCandidateResponse:
        """Return the exact validated candidate across the reviewer-only API boundary."""
        assessment = self._required_assessment(assessment_id)
        state = self._required_state(assessment_id)
        if state.candidate_result is None:
            raise PersistenceError
        try:
            result = AssessmentResult.model_validate(state.candidate_result)
        except ValidationError as exc:
            raise PersistenceError from exc
        return ReviewCandidateResponse(
            assessment_id=assessment_id,
            result=result,
            execution=state.candidate_execution,
            gate_result=state.gate_result,
            review_status=state.review_status,
            telemetry=state.telemetry,
            revision_count=state.revision_count,
            max_revisions=state.max_revisions,
            created_by_subject=assessment.created_by_subject,
            **self._review_actions(assessment, state, principal),
        )

    def list_candidate_versions(self, assessment_id: UUID) -> CandidateVersionsResponse:
        """Return every gated candidate with the feedback that produced each revision."""
        self._required_assessment(assessment_id)
        versions = self._reviews.list_candidate_versions(assessment_id)
        events = {
            event.review_id: event for event in self._reviews.list_review_events(assessment_id)
        }
        items: list[CandidateVersionItem] = []
        for version in versions:
            event = events.get(version.feedback_review_id) if version.feedback_review_id else None
            try:
                result = AssessmentResult.model_validate(version.result)
            except ValidationError as exc:
                raise PersistenceError from exc
            execution_mode = (version.execution or {}).get("execution_mode")
            items.append(
                CandidateVersionItem(
                    version_number=version.version_number,
                    created_at=version.created_at,
                    execution_mode=execution_mode if isinstance(execution_mode, str) else None,
                    gate_result=version.gate_result,
                    policy_fingerprint=version.policy_fingerprint,
                    result=result,
                    feedback=(
                        CandidateVersionFeedback(
                            review_id=event.review_id,
                            comment=event.comment,
                            reviewer_subject=event.reviewer_subject,
                        )
                        if event is not None
                        else None
                    ),
                )
            )
        return CandidateVersionsResponse(assessment_id=assessment_id, versions=items)

    def build_decision_record(self, assessment_id: UUID) -> DecisionRecordResponse:
        """Assemble an exportable record from persisted state only; no model is called."""
        assessment = self._required_assessment(assessment_id)
        versions = self._reviews.list_candidate_versions(assessment_id)
        events = self._reviews.list_review_events(assessment_id)
        events_by_id = {event.review_id: event for event in events}
        try:
            request = AssessmentRequest.model_validate(assessment.request_payload)
            final_result = (
                AssessmentResult.model_validate(assessment.result_payload)
                if assessment.result_payload is not None
                else None
            )
            latest_candidate = (
                AssessmentResult.model_validate(versions[-1].result) if versions else None
            )
        except ValidationError as exc:
            raise PersistenceError from exc

        if final_result is not None:
            evidence_source, evidence = "final_result", final_result.source_references
        elif latest_candidate is not None:
            evidence_source, evidence = "latest_candidate", latest_candidate.source_references
        else:
            evidence_source, evidence = "none", []
        execution = assessment.execution_metadata or (versions[-1].execution if versions else None)

        record_versions = []
        for version in versions:
            event = (
                events_by_id.get(version.feedback_review_id) if version.feedback_review_id else None
            )
            mode = (version.execution or {}).get("execution_mode")
            record_versions.append(
                DecisionRecordCandidateVersion(
                    version_number=version.version_number,
                    created_at=_utc(version.created_at),
                    execution_mode=mode if isinstance(mode, str) else None,
                    gate_result=version.gate_result,
                    policy_fingerprint=version.policy_fingerprint,
                    feedback=(
                        CandidateVersionFeedback(
                            review_id=event.review_id,
                            comment=event.comment,
                            reviewer_subject=event.reviewer_subject,
                        )
                        if event is not None
                        else None
                    ),
                )
            )
        unsigned = DecisionRecordResponse(
            assessment_id=assessment_id,
            generated_at=self._clock(),
            record_fingerprint="sha256:pending",
            current_policy_fingerprint=self._policy_fingerprint,
            input=DecisionRecordInput(
                request=request,
                created_by_subject=assessment.created_by_subject,
                created_at=_utc(assessment.created_at),
            ),
            routing=routing_from_execution(execution),
            evidence_source=evidence_source,
            evidence=evidence,
            candidate_versions=record_versions,
            reviews=[
                DecisionRecordReview(
                    review_id=event.review_id,
                    action=event.action,
                    previous_status=event.previous_status,
                    new_status=event.new_status,
                    reviewer_subject=event.reviewer_subject,
                    reviewer_role=event.reviewer_role,
                    reviewer_issuer=event.reviewer_issuer,
                    comment=event.comment,
                    reason_codes=event.reason_codes,
                    revision_number=event.revision_number,
                    created_at=_utc(event.created_at),
                )
                for event in events
            ],
            outcome=DecisionRecordOutcome(
                status=assessment.status,
                result=final_result,
                error_code=assessment.error_code,
                completed_at=_utc(assessment.completed_at) if assessment.completed_at else None,
            ),
        )
        canonical = json.dumps(
            unsigned.model_dump(mode="json", exclude={"generated_at", "record_fingerprint"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return unsigned.model_copy(update={"record_fingerprint": f"sha256:{digest}"})

    def approve(
        self,
        assessment_id: UUID,
        request: HumanReviewRequest,
        *,
        principal: AuthenticatedPrincipal | None = None,
    ) -> HumanReviewDecision:
        self._assert_independent_reviewer(assessment_id, principal, ReviewActionName.APPROVE)
        state = self._required_pending_state(assessment_id)
        if state.candidate_result is None:
            raise PersistenceError
        record = self._assessments.mark_completed(
            assessment_id, state.candidate_result, state.candidate_execution
        )
        if record is None:
            raise PersistenceError
        telemetry = self._review_telemetry(
            state, HumanReviewStatus.APPROVED, RuntimeTraceEventType.HUMAN_REVIEW_APPROVED
        )
        self._persist_transition(
            state=state,
            action=HumanReviewAction.APPROVED,
            new_status=HumanReviewStatus.APPROVED,
            request=request,
            telemetry=telemetry,
            principal=principal,
        )
        self._reviews.commit()
        self._export_telemetry(assessment_id, telemetry, state.gate_result)
        return self._decision(state, HumanReviewAction.APPROVED, record.status)

    def reject(
        self,
        assessment_id: UUID,
        request: HumanReviewRequest,
        *,
        principal: AuthenticatedPrincipal | None = None,
    ) -> HumanReviewDecision:
        self._assert_independent_reviewer(assessment_id, principal, ReviewActionName.REJECT)
        state = self._required_pending_state(assessment_id)
        record = self._assessments.mark_failed(
            assessment_id,
            error_code="human_review_rejected",
            error_message="The assessment was rejected during human review.",
        )
        if record is None:
            raise PersistenceError
        telemetry = self._review_telemetry(
            state, HumanReviewStatus.REJECTED, RuntimeTraceEventType.HUMAN_REVIEW_REJECTED
        ).model_copy(
            update={
                "execution_health": ExecutionHealth.BLOCKED,
                "termination_reason": "human_rejection",
            }
        )
        self._persist_transition(
            state=state,
            action=HumanReviewAction.REJECTED,
            new_status=HumanReviewStatus.REJECTED,
            request=request,
            telemetry=telemetry,
            principal=principal,
        )
        self._reviews.commit()
        self._export_telemetry(assessment_id, telemetry, state.gate_result)
        return self._decision(state, HumanReviewAction.REJECTED, record.status)

    def request_revision(
        self,
        assessment_id: UUID,
        request: HumanReviewRequest,
        *,
        principal: AuthenticatedPrincipal | None = None,
    ) -> HumanReviewDecision:
        self._assert_independent_reviewer(
            assessment_id, principal, ReviewActionName.REQUEST_REVISION
        )
        state = self._required_pending_state(assessment_id)
        if state.revision_count >= state.max_revisions:
            raise RevisionLimitReachedError
        revision = state.revision_count + 1
        telemetry = self._review_telemetry(
            state,
            HumanReviewStatus.REVISION_REQUESTED,
            RuntimeTraceEventType.REVISION_REQUESTED,
        )
        self._reviews.save_state(
            assessment_id=assessment_id,
            gate_result=state.gate_result,
            review_status=HumanReviewStatus.REVISION_REQUESTED,
            candidate_result=state.candidate_result,
            candidate_execution=state.candidate_execution,
            telemetry=telemetry,
            revision_count=revision,
            max_revisions=state.max_revisions,
        )
        self._reviews.add_review_event(
            assessment_id=assessment_id,
            action=HumanReviewAction.REVISION_REQUESTED,
            previous_status=HumanReviewStatus.PENDING,
            new_status=HumanReviewStatus.REVISION_REQUESTED,
            reviewer_id=(
                principal.subject if principal is not None else self._legacy_reviewer(request)
            ),
            comment=request.comment,
            reason_codes=state.gate_result.reason_codes,
            revision_number=revision,
            **self._actor_fields(principal),
        )
        self._reviews.commit()
        self._export_telemetry(assessment_id, telemetry, state.gate_result)
        return HumanReviewDecision(
            assessment_id=assessment_id,
            action=HumanReviewAction.REVISION_REQUESTED,
            review_status=HumanReviewStatus.REVISION_REQUESTED,
            assessment_status=AssessmentStatus.PENDING_REVIEW.value,
            revision_count=revision,
        )

    def get_revision_feedback(self, assessment_id: UUID) -> HumanReviewRecord:
        """Return bounded reviewer feedback as untrusted data for a trusted revision path."""
        state = self._required_state(assessment_id)
        if state.review_status != HumanReviewStatus.REVISION_REQUESTED:
            raise InvalidReviewTransitionError
        event = next(
            (
                item
                for item in reversed(self._reviews.list_review_events(assessment_id))
                if item.action == HumanReviewAction.REVISION_REQUESTED
                and item.revision_number == state.revision_count
            ),
            None,
        )
        if event is None:
            raise PersistenceError
        return event

    def resume_revision(
        self,
        *,
        assessment_id: UUID,
        result: AssessmentResult,
        evidence: tuple[RetrievedEvidence, ...],
        execution: ExecutionMetadata,
        duration_ms: int,
        provenance_valid: bool = True,
        feedback_review_id: UUID | None = None,
    ) -> PersistedAssessment:
        """Persist a trusted regenerated candidate; reviewer text is never executed here."""
        state = self._required_state(assessment_id, for_update=True)
        if state.review_status != HumanReviewStatus.REVISION_REQUESTED:
            raise InvalidReviewTransitionError
        previous = state.review_status
        record = self.process_candidate(
            assessment_id=assessment_id,
            result=result,
            evidence=evidence,
            execution=execution,
            duration_ms=duration_ms,
            provenance_valid=provenance_valid,
            revision_count=state.revision_count,
            record_review_request=False,
            feedback_review_id=feedback_review_id,
        )
        new_state = self._required_state(assessment_id)
        resumed_at = self._clock()
        wait_ms = max(0, round((resumed_at - state.updated_at).total_seconds() * 1_000))
        merged_telemetry = new_state.telemetry.model_copy(
            update={
                "human_wait_duration_ms": wait_ms,
                "total_duration_ms": new_state.telemetry.execution_duration_ms + wait_ms,
                "events": [
                    *state.telemetry.events,
                    RuntimeTraceEvent(
                        timestamp=resumed_at,
                        request_id=new_state.telemetry.request_id,
                        event_type=RuntimeTraceEventType.HUMAN_REVIEW_RESUMED,
                        component="human_review",
                        status="revision_submitted",
                    ),
                    *new_state.telemetry.events,
                ],
            }
        )
        self._reviews.save_state(
            assessment_id=assessment_id,
            gate_result=new_state.gate_result,
            review_status=new_state.review_status,
            candidate_result=new_state.candidate_result,
            candidate_execution=new_state.candidate_execution,
            telemetry=merged_telemetry,
            revision_count=new_state.revision_count,
            max_revisions=new_state.max_revisions,
        )
        self._reviews.add_review_event(
            assessment_id=assessment_id,
            action=HumanReviewAction.REVISION_SUBMITTED,
            previous_status=previous,
            new_status=new_state.review_status,
            reviewer_id=None,
            comment=None,
            reason_codes=new_state.gate_result.reason_codes,
            revision_number=state.revision_count,
        )
        self._reviews.commit()
        self._export_telemetry(assessment_id, merged_telemetry, new_state.gate_result)
        return record

    @staticmethod
    def derive_signals(
        *,
        result: AssessmentResult,
        evidence: tuple[RetrievedEvidence, ...],
        execution: ExecutionMetadata,
        provenance_valid: bool,
    ) -> QualityGateSignals:
        severity_order = {
            RiskSeverity.LOW: RuntimeRiskLevel.LOW,
            RiskSeverity.MEDIUM: RuntimeRiskLevel.MEDIUM,
            RiskSeverity.HIGH: RuntimeRiskLevel.HIGH,
            RiskSeverity.CRITICAL: RuntimeRiskLevel.CRITICAL,
        }
        risk_level = max(
            (severity_order[risk.severity] for risk in result.risks),
            default=RuntimeRiskLevel.LOW,
            key=lambda value: list(RuntimeRiskLevel).index(value),
        )
        degraded = False
        specialist_unavailable = False
        retrieval_failed = False
        tool_failed = False
        graph = getattr(execution, "graph_retrieval", None)
        if graph is not None:
            degraded = graph.degraded_graph_mode
            retrieval_failed = bool(graph.graph_error_code or graph.vector_error_code)
        if isinstance(execution, AssessmentExecutionMetadata):
            degraded = degraded or execution.termination_reason.value not in {
                "completed",
                "agent_stopped",
            }
            tool_failed = any(
                event.event_type == AgentTraceEventType.TOOL_FAILED for event in execution.trace
            )
        elif isinstance(execution, MultiAgentExecutionMetadata):
            degraded = degraded or execution.degraded_mode
            specialist_unavailable = any(
                status in {MultiAgentStatus.FAILED, MultiAgentStatus.SKIPPED}
                for status in execution.agent_statuses.model_dump().values()
            )
            tool_failed = any(
                event.event_type == MultiAgentTraceEventType.TOOL_FAILED
                for event in execution.trace
            )
        evidence_required = risk_level in {RuntimeRiskLevel.HIGH, RuntimeRiskLevel.CRITICAL}
        return QualityGateSignals(
            risk_level=risk_level,
            evidence_required=evidence_required,
            evidence_available=bool(evidence),
            provenance_valid=provenance_valid,
            degraded_execution=degraded,
            specialist_unavailable=specialist_unavailable,
            retrieval_failed=retrieval_failed,
            tool_failed=tool_failed,
            human_oversight_required=evidence_required,
            human_oversight_present=result.human_oversight.review_recommended,
            mitigations_complete=all(risk.mitigation.strip() for risk in result.risks),
        )

    def _is_self_review(
        self,
        assessment: PersistedAssessment,
        principal: AuthenticatedPrincipal | None,
    ) -> bool:
        if not self._enforce_separation_of_duties or principal is None:
            return False
        creator = assessment.created_by_subject
        return creator is not None and creator == principal.subject

    def _assert_independent_reviewer(
        self,
        assessment_id: UUID,
        principal: AuthenticatedPrincipal | None,
        action: ReviewActionName,
    ) -> None:
        assessment = self._required_assessment(assessment_id)
        if self._is_self_review(assessment, principal):
            logger.warning(
                "self_review_denied",
                extra={"assessment_id": str(assessment_id), "action": action.value},
            )
            raise SelfReviewForbiddenError

    def _review_actions(
        self,
        assessment: PersistedAssessment,
        state: RuntimeAssessmentState,
        principal: AuthenticatedPrincipal | None,
    ) -> dict[str, Any]:
        allowed: list[ReviewActionName] = []
        denied: list[DeniedReviewAction] = []
        for action in SEPARATION_OF_DUTIES_ACTIONS:
            code: str | None = None
            if state.review_status != HumanReviewStatus.PENDING:
                code = InvalidReviewTransitionError.error_code
            elif self._is_self_review(assessment, principal):
                code = SelfReviewForbiddenError.error_code
            elif (
                action == ReviewActionName.REQUEST_REVISION
                and state.revision_count >= state.max_revisions
            ):
                code = RevisionLimitReachedError.error_code
            if code is None:
                allowed.append(action)
            else:
                denied.append(DeniedReviewAction(action=action, code=code))
        return {"allowed_actions": allowed, "denied_actions": denied}

    def _required_assessment(self, assessment_id: UUID) -> PersistedAssessment:
        record = self._assessments.get_by_id(assessment_id)
        if record is None:
            raise AssessmentNotFoundError
        return record

    def _export_telemetry(
        self,
        assessment_id: UUID,
        telemetry: OperationalTelemetry,
        gate_result: QualityGateResult,
    ) -> None:
        try:
            self._telemetry_exporter.export(
                assessment_id=assessment_id,
                telemetry=telemetry,
                gate_result=gate_result,
            )
        except Exception as exc:
            logger.warning(
                "operational_telemetry_export_failed",
                extra={"failure_type": type(exc).__name__},
            )

    def _required_state(
        self, assessment_id: UUID, *, for_update: bool = False
    ) -> RuntimeAssessmentState:
        self._required_assessment(assessment_id)
        try:
            state = self._reviews.get_state(assessment_id, for_update=for_update)
        except (TypeError, ValueError) as exc:
            raise PersistenceError from exc
        if state is None:
            raise RuntimeStateNotFoundError
        return state

    def _required_pending_state(self, assessment_id: UUID) -> RuntimeAssessmentState:
        state = self._required_state(assessment_id, for_update=True)
        if state.review_status != HumanReviewStatus.PENDING:
            raise InvalidReviewTransitionError
        return state

    def _persist_transition(
        self,
        *,
        state: RuntimeAssessmentState,
        action: HumanReviewAction,
        new_status: HumanReviewStatus,
        request: HumanReviewRequest,
        telemetry: OperationalTelemetry,
        principal: AuthenticatedPrincipal | None,
    ) -> None:
        self._reviews.save_state(
            assessment_id=state.assessment_id,
            gate_result=state.gate_result,
            review_status=new_status,
            candidate_result=state.candidate_result,
            candidate_execution=state.candidate_execution,
            telemetry=telemetry,
            revision_count=state.revision_count,
            max_revisions=state.max_revisions,
        )
        self._reviews.add_review_event(
            assessment_id=state.assessment_id,
            action=action,
            previous_status=HumanReviewStatus.PENDING,
            new_status=new_status,
            reviewer_id=(
                principal.subject if principal is not None else self._legacy_reviewer(request)
            ),
            comment=request.comment,
            reason_codes=state.gate_result.reason_codes,
            revision_number=state.revision_count,
            **self._actor_fields(principal),
        )

    @staticmethod
    def _actor_fields(principal: AuthenticatedPrincipal | None) -> dict[str, str | None]:
        if principal is None:
            return {}
        return {
            "reviewer_subject": principal.subject,
            "reviewer_email": principal.email,
            "reviewer_role": principal.audit_role.value,
            "reviewer_issuer": principal.issuer,
            "request_id": get_request_id(),
        }

    @staticmethod
    def _legacy_reviewer(request: HumanReviewRequest) -> str | None:
        return request.model_dump().get("reviewer_id")

    def _review_telemetry(
        self,
        state: RuntimeAssessmentState,
        review_status: HumanReviewStatus,
        event_type: RuntimeTraceEventType,
    ) -> OperationalTelemetry:
        now = self._clock()
        wait_ms = max(0, round((now - state.updated_at).total_seconds() * 1_000))
        updated = state.telemetry.model_copy(
            update={
                "human_review_status": review_status,
                "human_wait_duration_ms": wait_ms,
                "total_duration_ms": state.telemetry.execution_duration_ms + wait_ms,
                "execution_health": (
                    ExecutionHealth.FULL
                    if review_status == HumanReviewStatus.APPROVED
                    else state.telemetry.execution_health
                ),
            }
        )
        updated = self._append_event(
            updated,
            RuntimeTraceEventType.HUMAN_REVIEW_RESUMED,
            review_status.value,
        )
        return self._append_event(
            updated,
            event_type,
            review_status.value,
        )

    def _append_event(
        self,
        telemetry: OperationalTelemetry,
        event_type: RuntimeTraceEventType,
        status: str,
        *,
        component: str = "human_review",
    ) -> OperationalTelemetry:
        return telemetry.model_copy(
            update={
                "events": [
                    *telemetry.events,
                    RuntimeTraceEvent(
                        timestamp=self._clock(),
                        request_id=telemetry.request_id,
                        event_type=event_type,
                        component=component,
                        status=status,
                    ),
                ]
            }
        )

    @staticmethod
    def _decision(
        state: RuntimeAssessmentState,
        action: HumanReviewAction,
        assessment_status: AssessmentStatus,
    ) -> HumanReviewDecision:
        return HumanReviewDecision(
            assessment_id=state.assessment_id,
            action=action,
            review_status=(
                HumanReviewStatus.APPROVED
                if action == HumanReviewAction.APPROVED
                else HumanReviewStatus.REJECTED
            ),
            assessment_status=assessment_status.value,
            revision_count=state.revision_count,
        )


def _utc(value: datetime) -> datetime:
    """Normalize persisted timestamps (SQLite returns naive values) to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
