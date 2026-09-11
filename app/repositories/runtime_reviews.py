"""Repository for persisted V7C gate state and immutable-style review history."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.assessment import utc_now
from app.db.models.runtime_review import AssessmentRuntimeStateModel, HumanReviewEventModel
from app.runtime.models import (
    HumanReviewAction,
    HumanReviewRecord,
    HumanReviewStatus,
    OperationalTelemetry,
    QualityGateResult,
    RuntimeAssessmentState,
    RuntimeReasonCode,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class RuntimeReviewRepository:
    """Persist one current checkpoint and append-only human decisions."""

    def __init__(
        self,
        session: Session,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._clock = clock

    def save_state(
        self,
        *,
        assessment_id: UUID,
        gate_result: QualityGateResult,
        review_status: HumanReviewStatus,
        candidate_result: Mapping[str, Any] | None,
        candidate_execution: Mapping[str, Any] | None,
        telemetry: OperationalTelemetry,
        revision_count: int,
        max_revisions: int,
    ) -> RuntimeAssessmentState:
        """Create or update the resumable checkpoint inside the caller transaction."""
        now = self._clock()
        telemetry_payload = {
            "gate_result": gate_result.model_dump(mode="json"),
            "operational": telemetry.model_dump(mode="json"),
        }
        model = self._session.get(AssessmentRuntimeStateModel, assessment_id)
        if model is None:
            model = AssessmentRuntimeStateModel(
                assessment_id=assessment_id,
                created_at=now,
                gate_decision=gate_result.decision.value,
                review_status=review_status.value,
                reason_codes=[item.value for item in gate_result.reason_codes],
                candidate_result=(dict(candidate_result) if candidate_result is not None else None),
                candidate_execution=(
                    dict(candidate_execution) if candidate_execution is not None else None
                ),
                telemetry=telemetry_payload,
                revision_count=revision_count,
                max_revisions=max_revisions,
                updated_at=now,
            )
            self._session.add(model)
        else:
            model.gate_decision = gate_result.decision.value
            model.review_status = review_status.value
            model.reason_codes = [item.value for item in gate_result.reason_codes]
            model.candidate_result = (
                dict(candidate_result) if candidate_result is not None else None
            )
            model.candidate_execution = (
                dict(candidate_execution) if candidate_execution is not None else None
            )
            model.telemetry = telemetry_payload
            model.revision_count = revision_count
            model.max_revisions = max_revisions
            model.updated_at = now
        self._session.flush()
        return _state_from_model(model)

    def get_state(
        self, assessment_id: UUID, *, for_update: bool = False
    ) -> RuntimeAssessmentState | None:
        """Return the current persisted checkpoint."""
        statement = select(AssessmentRuntimeStateModel).where(
            AssessmentRuntimeStateModel.assessment_id == assessment_id
        )
        if for_update:
            statement = statement.with_for_update()
        model = self._session.scalars(statement).one_or_none()
        return _state_from_model(model) if model is not None else None

    def add_review_event(
        self,
        *,
        assessment_id: UUID,
        action: HumanReviewAction,
        previous_status: HumanReviewStatus,
        new_status: HumanReviewStatus,
        reviewer_id: str | None,
        comment: str | None,
        reason_codes: list[RuntimeReasonCode],
        revision_number: int,
        reviewer_subject: str | None = None,
        reviewer_email: str | None = None,
        reviewer_role: str | None = None,
        reviewer_issuer: str | None = None,
        request_id: str | None = None,
    ) -> HumanReviewRecord:
        """Append a review event; existing rows are never updated."""
        model = HumanReviewEventModel(
            id=uuid4(),
            assessment_id=assessment_id,
            action=action.value,
            previous_status=previous_status.value,
            new_status=new_status.value,
            reviewer_id=reviewer_id,
            reviewer_subject=reviewer_subject,
            reviewer_email=reviewer_email,
            reviewer_role=reviewer_role,
            reviewer_issuer=reviewer_issuer,
            request_id=request_id,
            comment=comment,
            reason_codes=[item.value for item in reason_codes],
            revision_number=revision_number,
            created_at=self._clock(),
        )
        self._session.add(model)
        self._session.flush()
        return _review_from_model(model)

    def list_review_events(self, assessment_id: UUID) -> list[HumanReviewRecord]:
        """Return the full audit history in creation and UUID order."""
        models = self._session.scalars(
            select(HumanReviewEventModel)
            .where(HumanReviewEventModel.assessment_id == assessment_id)
            .order_by(HumanReviewEventModel.created_at, HumanReviewEventModel.id)
        ).all()
        return [_review_from_model(model) for model in models]

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()


def _state_from_model(model: AssessmentRuntimeStateModel) -> RuntimeAssessmentState:
    persisted_gate = model.telemetry.get("gate_result")
    persisted_operational = model.telemetry.get("operational")
    if not isinstance(persisted_gate, dict) or not isinstance(persisted_operational, dict):
        raise ValueError("Persisted runtime checkpoint is structurally invalid")
    gate = QualityGateResult.model_validate(persisted_gate)
    return RuntimeAssessmentState(
        assessment_id=model.assessment_id,
        gate_result=gate,
        review_status=HumanReviewStatus(model.review_status),
        candidate_result=(dict(model.candidate_result) if model.candidate_result else None),
        candidate_execution=(
            dict(model.candidate_execution) if model.candidate_execution else None
        ),
        telemetry=OperationalTelemetry.model_validate(persisted_operational),
        revision_count=model.revision_count,
        max_revisions=model.max_revisions,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _review_from_model(model: HumanReviewEventModel) -> HumanReviewRecord:
    return HumanReviewRecord(
        review_id=model.id,
        assessment_id=model.assessment_id,
        action=HumanReviewAction(model.action),
        previous_status=HumanReviewStatus(model.previous_status),
        new_status=HumanReviewStatus(model.new_status),
        reviewer_id=model.reviewer_id,
        reviewer_subject=model.reviewer_subject,
        reviewer_email=model.reviewer_email,
        reviewer_role=model.reviewer_role,
        reviewer_issuer=model.reviewer_issuer,
        request_id=model.request_id,
        comment=model.comment,
        reason_codes=[RuntimeReasonCode(item) for item in model.reason_codes],
        revision_number=model.revision_number,
        created_at=_as_utc(model.created_at),
    )
