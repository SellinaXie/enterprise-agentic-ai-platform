"""Deterministic portfolio demo seed verification."""

from sqlalchemy.orm import Session

from app.demo.seed import seed_demo_scenarios
from app.models.assessment import AssessmentStatus
from app.repositories.runtime_reviews import RuntimeReviewRepository
from app.runtime.models import HumanReviewStatus, RuntimeRiskDecision


def test_demo_seed_creates_review_and_auto_complete_paths(db_session: Session) -> None:
    seeded = seed_demo_scenarios(db_session)

    assert [item.scenario for item in seeded] == [
        "high-risk-customer-pii",
        "low-risk-internal-assistant",
    ]
    assert [item.status for item in seeded] == [
        AssessmentStatus.PENDING_REVIEW,
        AssessmentStatus.COMPLETED,
    ]
    reviews = RuntimeReviewRepository(db_session)
    high_state = reviews.get_state(seeded[0].assessment_id)
    low_state = reviews.get_state(seeded[1].assessment_id)
    assert high_state is not None
    assert high_state.gate_result.decision == RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW
    assert high_state.review_status == HumanReviewStatus.PENDING
    assert low_state is not None
    assert low_state.gate_result.decision == RuntimeRiskDecision.AUTO_COMPLETE
    assert low_state.review_status == HumanReviewStatus.NOT_REQUIRED
