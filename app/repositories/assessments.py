"""SQLAlchemy repository for assessment application state."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models.assessment import AssessmentModel, utc_now
from app.models.assessment import AssessmentStatus
from app.models.persisted_assessment import PersistedAssessment


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_record(model: AssessmentModel) -> PersistedAssessment:
    created_at = _as_utc(model.created_at)
    updated_at = _as_utc(model.updated_at)
    if created_at is None or updated_at is None:
        raise ValueError("Persisted assessment timestamps must not be null")

    return PersistedAssessment(
        assessment_id=model.id,
        status=model.status,
        request_payload=dict(model.request_payload),
        result_payload=dict(model.result_payload) if model.result_payload is not None else None,
        execution_metadata=(
            dict(model.execution_metadata) if model.execution_metadata is not None else None
        ),
        error_code=model.error_code,
        error_message=model.error_message,
        created_at=created_at,
        updated_at=updated_at,
        completed_at=_as_utc(model.completed_at),
        created_by_subject=model.created_by_subject,
    )


class AssessmentRepository:
    """Persist assessments without owning business workflow decisions."""

    def __init__(
        self,
        session: Session,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._clock = clock

    def create(
        self,
        *,
        assessment_id: UUID,
        company_name: str,
        industry: str,
        business_problem: str,
        request_payload: Mapping[str, Any],
        created_by_subject: str | None = None,
    ) -> PersistedAssessment:
        """Add a pending assessment and flush it into the current transaction."""
        now = self._clock()
        model = AssessmentModel(
            id=assessment_id,
            status=AssessmentStatus.PENDING,
            company_name=company_name,
            industry=industry,
            business_problem=business_problem,
            request_payload=dict(request_payload),
            created_by_subject=created_by_subject,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        self._session.flush()
        return _to_record(model)

    def get_by_id(self, assessment_id: UUID) -> PersistedAssessment | None:
        """Return an assessment domain record when it exists."""
        model = self._session.get(AssessmentModel, assessment_id)
        return _to_record(model) if model is not None else None

    def mark_processing(self, assessment_id: UUID) -> PersistedAssessment | None:
        """Move a pending assessment to processing."""
        model = self._session.get(AssessmentModel, assessment_id)
        if model is None:
            return None
        model.status = AssessmentStatus.PROCESSING
        model.updated_at = self._clock()
        self._session.flush()
        return _to_record(model)

    def mark_completed(
        self,
        assessment_id: UUID,
        result_payload: Mapping[str, Any],
        execution_metadata: Mapping[str, Any] | None = None,
    ) -> PersistedAssessment | None:
        """Persist a validated result and mark the assessment completed."""
        model = self._session.get(AssessmentModel, assessment_id)
        if model is None:
            return None
        now = self._clock()
        model.status = AssessmentStatus.COMPLETED
        model.result_payload = dict(result_payload)
        model.execution_metadata = (
            dict(execution_metadata) if execution_metadata is not None else None
        )
        model.error_code = None
        model.error_message = None
        model.completed_at = now
        model.updated_at = now
        self._session.flush()
        return _to_record(model)

    def mark_pending_review(
        self,
        assessment_id: UUID,
        execution_metadata: Mapping[str, Any] | None = None,
    ) -> PersistedAssessment | None:
        """Pause finalization while the candidate remains in runtime checkpoint storage."""
        model = self._session.get(AssessmentModel, assessment_id)
        if model is None:
            return None
        model.status = AssessmentStatus.PENDING_REVIEW
        model.result_payload = None
        model.execution_metadata = (
            dict(execution_metadata) if execution_metadata is not None else None
        )
        model.error_code = None
        model.error_message = None
        model.completed_at = None
        model.updated_at = self._clock()
        self._session.flush()
        return _to_record(model)

    def mark_failed(
        self,
        assessment_id: UUID,
        *,
        error_code: str,
        error_message: str,
    ) -> PersistedAssessment | None:
        """Persist only safe failure metadata and mark the assessment failed."""
        model = self._session.get(AssessmentModel, assessment_id)
        if model is None:
            return None
        model.status = AssessmentStatus.FAILED
        model.result_payload = None
        model.execution_metadata = None
        model.error_code = error_code[:100]
        model.error_message = error_message[:500]
        model.completed_at = None
        model.updated_at = self._clock()
        self._session.flush()
        return _to_record(model)

    def commit(self) -> None:
        """Commit the service-selected transaction boundary."""
        self._session.commit()

    def rollback(self) -> None:
        """Roll back the active transaction after a persistence failure."""
        self._session.rollback()
