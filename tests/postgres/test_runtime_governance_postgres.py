"""Real PostgreSQL verification for V7C checkpoints and review audit history."""

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.agents.models import DeterministicExecutionMetadata
from app.core.context import reset_request_id, set_request_id
from app.identity.models import AuthenticatedPrincipal, Role
from app.models.assessment import AssessmentStatus
from app.repositories.assessments import AssessmentRepository
from app.repositories.runtime_reviews import RuntimeReviewRepository
from app.runtime.gate import RuntimeRiskGate
from app.runtime.models import HumanReviewAction, HumanReviewRequest, RuntimeRiskPolicy
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from app.services.runtime_governance import RuntimeGovernanceService

pytestmark = pytest.mark.postgres


def test_postgres_checkpoint_jsonb_timestamptz_and_review_resume(
    postgres_session_factory: sessionmaker[Session],
    synthetic_assessment_request: AssessmentRequest,
    synthetic_assessment_result: AssessmentResult,
) -> None:
    with postgres_session_factory() as session:
        assessments = AssessmentRepository(session)
        reviews = RuntimeReviewRepository(session)
        service = RuntimeGovernanceService(
            assessments=assessments,
            reviews=reviews,
            gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        )
        assessment_id = assessments.create(
            assessment_id=uuid4(),
            company_name=synthetic_assessment_request.company_name,
            industry=synthetic_assessment_request.industry,
            business_problem=synthetic_assessment_request.business_problem,
            request_payload=synthetic_assessment_request.model_dump(mode="json"),
        ).assessment_id
        assessments.mark_processing(assessment_id)
        paused = service.process_candidate(
            assessment_id=assessment_id,
            result=synthetic_assessment_result,
            evidence=(),
            execution=DeterministicExecutionMetadata(),
            duration_ms=5,
        )
        assessments.commit()

    with postgres_session_factory() as session:
        state = RuntimeReviewRepository(session).get_state(assessment_id)
        assert state is not None
        assert state.created_at.utcoffset() is not None
        assert state.candidate_result is not None
        service = RuntimeGovernanceService(
            assessments=AssessmentRepository(session),
            reviews=RuntimeReviewRepository(session),
            gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        )
        decision = service.approve(
            assessment_id,
            HumanReviewRequest(reviewer_id="postgres-synthetic-reviewer"),
        )
        history = RuntimeReviewRepository(session).list_review_events(assessment_id)

    assert paused.status == AssessmentStatus.PENDING_REVIEW
    assert decision.assessment_status == AssessmentStatus.COMPLETED.value
    assert [event.action for event in history] == [
        HumanReviewAction.REQUESTED,
        HumanReviewAction.APPROVED,
    ]


def test_authenticated_reviewer_identity_and_request_id_are_persisted(
    postgres_session_factory: sessionmaker[Session],
    synthetic_assessment_request: AssessmentRequest,
    synthetic_assessment_result: AssessmentResult,
) -> None:
    principal = AuthenticatedPrincipal(
        subject="reviewer-subject-456",
        email="reviewer@identity.test",
        display_name="Synthetic Reviewer",
        roles=frozenset({Role.REVIEWER}),
        issuer="https://identity.test.invalid/",
    )
    with postgres_session_factory() as session:
        assessments = AssessmentRepository(session)
        reviews = RuntimeReviewRepository(session)
        service = RuntimeGovernanceService(
            assessments=assessments,
            reviews=reviews,
            gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        )
        assessment_id = assessments.create(
            assessment_id=uuid4(),
            company_name=synthetic_assessment_request.company_name,
            industry=synthetic_assessment_request.industry,
            business_problem=synthetic_assessment_request.business_problem,
            request_payload=synthetic_assessment_request.model_dump(mode="json"),
            created_by_subject="analyst-subject-123",
        ).assessment_id
        assessments.mark_processing(assessment_id)
        service.process_candidate(
            assessment_id=assessment_id,
            result=synthetic_assessment_result,
            evidence=(),
            execution=DeterministicExecutionMetadata(),
            duration_ms=5,
        )
        assessments.commit()

        request_context = set_request_id("postgres-review-request-1")
        try:
            service.approve(
                assessment_id,
                HumanReviewRequest(reviewer_id="spoofed-client-identity"),
                principal=principal,
            )
        finally:
            reset_request_id(request_context)

    with postgres_session_factory() as session:
        assessment = AssessmentRepository(session).get_by_id(assessment_id)
        history = RuntimeReviewRepository(session).list_review_events(assessment_id)

    approved = history[-1]
    assert assessment is not None
    assert assessment.created_by_subject == "analyst-subject-123"
    assert approved.reviewer_id == principal.subject
    assert approved.reviewer_subject == principal.subject
    assert approved.reviewer_email == principal.email
    assert approved.reviewer_role == "reviewer"
    assert approved.reviewer_issuer == principal.issuer
    assert approved.request_id == "postgres-review-request-1"


def test_postgres_revision_history_survives_session_boundaries(
    postgres_session_factory: sessionmaker[Session],
    synthetic_assessment_request: AssessmentRequest,
    synthetic_assessment_result: AssessmentResult,
) -> None:
    """Persist revision count, bounded feedback, resumption, and append-only history."""
    with postgres_session_factory() as session:
        assessments = AssessmentRepository(session)
        assessment_id = assessments.create(
            assessment_id=uuid4(),
            company_name=synthetic_assessment_request.company_name,
            industry=synthetic_assessment_request.industry,
            business_problem=synthetic_assessment_request.business_problem,
            request_payload=synthetic_assessment_request.model_dump(mode="json"),
        ).assessment_id
        assessments.mark_processing(assessment_id)
        RuntimeGovernanceService(
            assessments=assessments,
            reviews=RuntimeReviewRepository(session),
            gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        ).process_candidate(
            assessment_id=assessment_id,
            result=synthetic_assessment_result,
            evidence=(),
            execution=DeterministicExecutionMetadata(),
            duration_ms=4,
        )
        assessments.commit()

    with postgres_session_factory() as session:
        RuntimeGovernanceService(
            assessments=AssessmentRepository(session),
            reviews=RuntimeReviewRepository(session),
            gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        ).request_revision(
            assessment_id,
            HumanReviewRequest(
                reviewer_id="postgres-reviewer",
                comment="Clarify the synthetic mitigation before approval.",
            ),
        )

    with postgres_session_factory() as session:
        service = RuntimeGovernanceService(
            assessments=AssessmentRepository(session),
            reviews=RuntimeReviewRepository(session),
            gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        )
        feedback = service.get_revision_feedback(assessment_id)
        resumed = service.resume_revision(
            assessment_id=assessment_id,
            result=synthetic_assessment_result,
            evidence=(),
            execution=DeterministicExecutionMetadata(),
            duration_ms=3,
        )
        assert feedback.comment == "Clarify the synthetic mitigation before approval."
        assert resumed.status == AssessmentStatus.PENDING_REVIEW

    with postgres_session_factory() as session:
        service = RuntimeGovernanceService(
            assessments=AssessmentRepository(session),
            reviews=RuntimeReviewRepository(session),
            gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        )
        service.approve(
            assessment_id,
            HumanReviewRequest(reviewer_id="postgres-reviewer"),
        )
        state = RuntimeReviewRepository(session).get_state(assessment_id)
        history = RuntimeReviewRepository(session).list_review_events(assessment_id)

    assert state is not None and state.revision_count == 1
    assert [event.action for event in history] == [
        HumanReviewAction.REQUESTED,
        HumanReviewAction.REVISION_REQUESTED,
        HumanReviewAction.REVISION_SUBMITTED,
        HumanReviewAction.APPROVED,
    ]
