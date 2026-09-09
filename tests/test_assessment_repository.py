"""Assessment repository lifecycle tests."""

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.models.assessment import AssessmentStatus
from app.repositories.assessments import AssessmentRepository
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from tests.factories import build_assessment_result


def build_request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual review takes too long",
        desired_outcome="Reduce turnaround time",
    )


def create_record(
    repository: AssessmentRepository,
    request: AssessmentRequest,
) -> UUID:
    assessment_id = uuid4()
    repository.create(
        assessment_id=assessment_id,
        company_name=request.company_name,
        industry=request.industry,
        business_problem=request.business_problem,
        request_payload=request.model_dump(mode="json"),
    )
    repository.commit()
    return assessment_id


def test_create_and_get_assessment(db_session: Session) -> None:
    repository = AssessmentRepository(db_session)
    request = build_request()

    assessment_id = create_record(repository, request)
    retrieved = repository.get_by_id(assessment_id)

    assert retrieved is not None
    assert retrieved.assessment_id == assessment_id
    assert retrieved.status == AssessmentStatus.PENDING
    assert retrieved.request_payload == request.model_dump(mode="json")


def test_get_unknown_assessment_returns_none(db_session: Session) -> None:
    repository = AssessmentRepository(db_session)

    assert repository.get_by_id(uuid4()) is None


def test_mark_processing_and_completed(db_session: Session) -> None:
    repository = AssessmentRepository(db_session)
    assessment_id = create_record(repository, build_request())

    processing = repository.mark_processing(assessment_id)
    repository.commit()
    completed = repository.mark_completed(
        assessment_id,
        build_assessment_result().model_dump(mode="json"),
    )
    repository.commit()

    assert processing is not None
    assert processing.status == AssessmentStatus.PROCESSING
    assert completed is not None
    assert completed.status == AssessmentStatus.COMPLETED
    assert completed.completed_at is not None
    assert AssessmentResult.model_validate(completed.result_payload) == build_assessment_result()


def test_mark_failed_stores_only_safe_error(db_session: Session) -> None:
    repository = AssessmentRepository(db_session)
    assessment_id = create_record(repository, build_request())
    repository.mark_processing(assessment_id)
    repository.commit()

    failed = repository.mark_failed(
        assessment_id,
        error_code="llm_provider_error",
        error_message="AI assessment generation is temporarily unavailable. Please try again.",
    )
    repository.commit()

    assert failed is not None
    assert failed.status == AssessmentStatus.FAILED
    assert failed.result_payload is None
    assert failed.error_code == "llm_provider_error"
    assert failed.completed_at is None
