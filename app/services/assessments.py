"""Assessment application service."""

import logging
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.core.exceptions import (
    ApplicationError,
    AssessmentGenerationError,
    AssessmentNotFoundError,
    DatabaseUnavailableError,
    PersistenceError,
)
from app.models.persisted_assessment import PersistedAssessment
from app.schemas.assessment import (
    AssessmentFailure,
    AssessmentRequest,
    AssessmentResponse,
    AssessmentResult,
)
from app.services.assessment_prompt import AssessmentPrompt, build_assessment_prompt

logger = logging.getLogger(__name__)


class AssessmentGenerator(Protocol):
    """Provider-independent interface for structured assessment generation."""

    def generate(self, prompt: AssessmentPrompt) -> AssessmentResult:
        """Generate a validated assessment result."""
        ...


class AssessmentRepositoryProtocol(Protocol):
    """Persistence operations required by the assessment workflow."""

    def create(
        self,
        *,
        assessment_id: UUID,
        company_name: str,
        industry: str,
        business_problem: str,
        request_payload: dict[str, Any],
    ) -> PersistedAssessment: ...

    def get_by_id(self, assessment_id: UUID) -> PersistedAssessment | None: ...

    def mark_processing(self, assessment_id: UUID) -> PersistedAssessment | None: ...

    def mark_completed(
        self,
        assessment_id: UUID,
        result_payload: dict[str, Any],
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


class AssessmentService:
    """Coordinate generation and explicit persistence transaction boundaries."""

    def __init__(
        self,
        generator: AssessmentGenerator,
        repository: AssessmentRepositoryProtocol,
    ) -> None:
        self._generator = generator
        self._repository = repository

    def generate_assessment(self, request: AssessmentRequest) -> AssessmentResponse:
        """Persist lifecycle state around synchronous structured generation."""
        assessment_id = uuid4()
        log_context = {"assessment_id": str(assessment_id)}

        request_payload = request.model_dump(mode="json")
        try:
            self._repository.create(
                assessment_id=assessment_id,
                company_name=request.company_name,
                industry=request.industry,
                business_problem=request.business_problem,
                request_payload=request_payload,
            )
            self._repository.commit()
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc

        logger.info("assessment_record_created", extra={**log_context, "status": "pending"})

        try:
            processing_record = self._repository.mark_processing(assessment_id)
            if processing_record is None:
                raise PersistenceError
            self._repository.commit()
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc

        logger.info("assessment_marked_processing", extra={**log_context, "status": "processing"})
        logger.info("assessment_generation_started", extra=log_context)

        try:
            result = self._generator.generate(build_assessment_prompt(request))
        except ApplicationError as exc:
            self._persist_failure(
                assessment_id,
                error_code=exc.error_code,
                error_message=exc.public_message,
            )
            logger.warning(
                "assessment_failed",
                extra={**log_context, "error_code": exc.error_code},
            )
            raise
        except Exception as exc:
            unexpected_error = AssessmentGenerationError()
            self._persist_failure(
                assessment_id,
                error_code=unexpected_error.error_code,
                error_message=unexpected_error.public_message,
            )
            logger.error(
                "assessment_failed",
                extra={
                    **log_context,
                    "error_code": unexpected_error.error_code,
                    "generation_error_type": type(exc).__name__,
                },
            )
            raise unexpected_error from exc

        try:
            completed_record = self._repository.mark_completed(
                assessment_id,
                result.model_dump(mode="json"),
            )
            if completed_record is None:
                raise PersistenceError
            self._repository.commit()
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc

        logger.info(
            "assessment_result_persisted",
            extra={**log_context, "status": "completed"},
        )
        logger.info(
            "assessment_completed",
            extra={**log_context, "status": "completed"},
        )
        return self._to_response(completed_record)

    def get_assessment(self, assessment_id: UUID) -> AssessmentResponse:
        """Retrieve and validate persisted assessment state by ID."""
        logger.info("assessment_retrieval_requested", extra={"assessment_id": str(assessment_id)})
        try:
            record = self._repository.get_by_id(assessment_id)
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc

        if record is None:
            logger.info("assessment_not_found", extra={"assessment_id": str(assessment_id)})
            raise AssessmentNotFoundError
        return self._to_response(record)

    def _persist_failure(
        self,
        assessment_id: UUID,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        try:
            failed_record = self._repository.mark_failed(
                assessment_id,
                error_code=error_code,
                error_message=error_message,
            )
            if failed_record is None:
                raise PersistenceError
            self._repository.commit()
        except SQLAlchemyError as exc:
            raise self._handle_database_error(exc) from exc
        logger.info(
            "assessment_failure_persisted",
            extra={
                "assessment_id": str(assessment_id),
                "status": "failed",
                "error_code": error_code,
            },
        )

    def _handle_database_error(self, exc: SQLAlchemyError) -> ApplicationError:
        try:
            self._repository.rollback()
        except SQLAlchemyError as rollback_exc:
            logger.error(
                "database_rollback_failed",
                extra={"database_error_type": type(rollback_exc).__name__},
            )

        logger.error(
            "database_failure",
            extra={"database_error_type": type(exc).__name__},
        )
        if isinstance(exc, OperationalError):
            return DatabaseUnavailableError()
        return PersistenceError()

    @staticmethod
    def _to_response(record: PersistedAssessment) -> AssessmentResponse:
        try:
            request = AssessmentRequest.model_validate(record.request_payload)
            result = (
                AssessmentResult.model_validate(record.result_payload)
                if record.result_payload is not None
                else None
            )
        except ValidationError as exc:
            raise PersistenceError from exc

        error = None
        if record.error_code is not None and record.error_message is not None:
            error = AssessmentFailure(code=record.error_code, message=record.error_message)

        return AssessmentResponse(
            assessment_id=record.assessment_id,
            status=record.status,
            input=request,
            result=result,
            error=error,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at,
        )
