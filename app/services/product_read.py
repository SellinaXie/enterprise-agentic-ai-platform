"""Read models for the V8C interface without moving business rules into the client."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.exceptions import DatabaseUnavailableError, PersistenceError
from app.models.assessment import AssessmentStatus
from app.models.persisted_assessment import PersistedAssessment
from app.runtime.models import RuntimeAssessmentState
from app.schemas.product import AssessmentListItem, AssessmentListResponse


class AssessmentReadRepository(Protocol):
    """Bounded assessment read operations required by the product UI."""

    def list_page(
        self,
        *,
        status: AssessmentStatus | None,
        offset: int,
        limit: int,
    ) -> list[PersistedAssessment]: ...

    def count(self, *, status: AssessmentStatus | None) -> int: ...

    def count_by_status(self) -> dict[str, int]: ...


class RuntimeReadRepository(Protocol):
    """Runtime checkpoint reads required by the product UI."""

    def get_states(self, assessment_ids: list[UUID]) -> dict[UUID, RuntimeAssessmentState]: ...

    def count_by_gate_decision(self) -> dict[str, int]: ...

    def count_by_review_status(self) -> dict[str, int]: ...


class ProductReadService:
    """Build safe compact read models over persisted backend state."""

    def __init__(
        self,
        *,
        assessments: AssessmentReadRepository,
        runtime: RuntimeReadRepository,
    ) -> None:
        self._assessments = assessments
        self._runtime = runtime

    def list_assessments(
        self,
        *,
        status: AssessmentStatus | None,
        offset: int,
        limit: int,
    ) -> AssessmentListResponse:
        """Return one bounded page and aggregate facets from authoritative storage."""
        try:
            records = self._assessments.list_page(status=status, offset=offset, limit=limit)
            runtime_states = self._runtime.get_states([record.assessment_id for record in records])
            return AssessmentListResponse(
                items=[
                    self._to_list_item(record, runtime_states.get(record.assessment_id))
                    for record in records
                ],
                total=self._assessments.count(status=status),
                offset=offset,
                limit=limit,
                status_counts=self._assessments.count_by_status(),
                runtime_decision_counts=self._runtime.count_by_gate_decision(),
                review_status_counts=self._runtime.count_by_review_status(),
            )
        except SQLAlchemyError as exc:
            if isinstance(exc, OperationalError):
                raise DatabaseUnavailableError from exc
            raise PersistenceError from exc

    @staticmethod
    def _to_list_item(
        record: PersistedAssessment,
        runtime: RuntimeAssessmentState | None,
    ) -> AssessmentListItem:
        request = record.request_payload
        execution = record.execution_metadata or {}
        execution_mode = execution.get("execution_mode")
        if execution_mode == "agentic":
            execution_mode = "single_agent"
        request_id = execution.get("request_id")
        return AssessmentListItem(
            assessment_id=record.assessment_id,
            company_name=str(request.get("company_name", "Unknown organization")),
            industry=str(request.get("industry", "Unknown industry")),
            business_problem=str(request.get("business_problem", "Assessment")),
            status=record.status,
            execution_mode=str(execution_mode) if execution_mode is not None else None,
            created_by_subject=record.created_by_subject,
            runtime_decision=runtime.gate_result.decision if runtime else None,
            risk_level=runtime.gate_result.risk_level if runtime else None,
            reason_codes=list(runtime.gate_result.reason_codes) if runtime else [],
            review_status=runtime.review_status if runtime else None,
            request_id=str(request_id) if request_id is not None else None,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )
