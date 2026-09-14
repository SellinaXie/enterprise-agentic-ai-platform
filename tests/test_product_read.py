"""V8C product read-model, evaluation, session, and reviewer-boundary tests."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.models import DeterministicExecutionMetadata
from app.models.assessment import AssessmentStatus
from app.repositories.assessments import AssessmentRepository
from app.repositories.runtime_reviews import RuntimeReviewRepository
from app.runtime.gate import RuntimeRiskGate
from app.runtime.models import RuntimeRiskPolicy
from app.schemas.assessment import AssessmentRequest
from app.services.product_read import ProductReadService
from app.services.runtime_governance import RuntimeGovernanceService
from tests.factories import build_assessment_result


def _request(company: str = "Synthetic Enterprise") -> AssessmentRequest:
    return AssessmentRequest(
        company_name=company,
        industry="Financial services",
        business_problem="Manual evidence review is slow",
        desired_outcome="Prepare governed review packages",
    )


def _create_processing(repository: AssessmentRepository, request: AssessmentRequest) -> str:
    assessment_id = uuid4()
    repository.create(
        assessment_id=assessment_id,
        company_name=request.company_name,
        industry=request.industry,
        business_problem=request.business_problem,
        request_payload=request.model_dump(mode="json"),
        created_by_subject="analyst-123",
    )
    repository.mark_processing(assessment_id)
    return str(assessment_id)


def test_product_read_service_returns_bounded_page_and_facets(db_session: Session) -> None:
    assessments = AssessmentRepository(db_session)
    reviews = RuntimeReviewRepository(db_session)
    first_id = _create_processing(assessments, _request("First Enterprise"))
    second_id = _create_processing(assessments, _request("Second Enterprise"))
    assessments.mark_completed(
        UUID(second_id),
        build_assessment_result().model_dump(mode="json"),
        DeterministicExecutionMetadata(request_id="product-read-1").model_dump(mode="json"),
    )
    assessments.commit()

    response = ProductReadService(assessments=assessments, runtime=reviews).list_assessments(
        status=None,
        offset=0,
        limit=1,
    )

    assert response.total == 2
    assert len(response.items) == 1
    assert response.status_counts == {"processing": 1, "completed": 1}
    assert str(response.items[0].assessment_id) in {first_id, second_id}
    assert response.items[0].company_name in {"First Enterprise", "Second Enterprise"}


def test_product_api_exposes_session_list_evaluation_and_reviewer_candidate(
    client: TestClient,
    db_session: Session,
) -> None:
    assessments = AssessmentRepository(db_session)
    reviews = RuntimeReviewRepository(db_session)
    assessment_id = _create_processing(assessments, _request())
    governance = RuntimeGovernanceService(
        assessments=assessments,
        reviews=reviews,
        gate=RuntimeRiskGate(RuntimeRiskPolicy()),
    )
    governance.process_candidate(
        assessment_id=UUID(assessment_id),
        result=build_assessment_result(),
        evidence=(),
        execution=DeterministicExecutionMetadata(request_id="product-api-1"),
        duration_ms=9,
    )
    assessments.commit()

    session_response = client.get("/api/v1/session")
    list_response = client.get("/api/v1/assessments?status=pending_review&limit=10")
    queue_response = client.get("/api/v1/reviews/pending")
    candidate_response = client.get(f"/api/v1/assessments/{assessment_id}/review-candidate")
    evaluation_response = client.get("/api/v1/evaluation/summary")

    assert session_response.status_code == 200
    assert session_response.json()["roles"] == ["admin"]
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1
    item = list_response.json()["items"][0]
    assert item["assessment_id"] == assessment_id
    assert item["runtime_decision"] == "require_human_review"
    assert item["review_status"] == "pending"
    assert queue_response.status_code == 200
    assert queue_response.json()["items"][0]["assessment_id"] == assessment_id
    assert candidate_response.status_code == 200
    assert candidate_response.json()["result"]["risks"][0]["severity"] == "high"
    assert candidate_response.json()["execution"]["request_id"] == "product-api-1"
    assert evaluation_response.status_code == 200
    assert [report["mode"] for report in evaluation_response.json()["v7a"]] == [
        "vector",
        "graph",
        "hybrid",
    ]
    assert [report["mode"] for report in evaluation_response.json()["v7b"]] == [
        "deterministic",
        "single_agent",
        "multi_agent",
    ]
    assert all(report["synthetic"] for report in evaluation_response.json()["v7b"])


def test_status_filter_never_changes_persisted_lifecycle(db_session: Session) -> None:
    assessments = AssessmentRepository(db_session)
    assessment_id = _create_processing(assessments, _request())
    assessments.commit()
    service = ProductReadService(
        assessments=assessments,
        runtime=RuntimeReviewRepository(db_session),
    )

    completed = service.list_assessments(
        status=AssessmentStatus.COMPLETED,
        offset=0,
        limit=10,
    )

    assert completed.total == 0
    persisted = assessments.get_by_id(UUID(assessment_id))
    assert persisted is not None and persisted.status == AssessmentStatus.PROCESSING
