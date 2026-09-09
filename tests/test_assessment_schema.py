"""Structured assessment schema smoke tests."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.assessment import AssessmentStatus
from app.schemas.assessment import AssessmentRequest, AssessmentResponse, AssessmentResult
from tests.factories import build_assessment_result


def test_structured_assessment_round_trips_through_pydantic() -> None:
    result = build_assessment_result()

    reparsed = AssessmentResult.model_validate_json(result.model_dump_json())

    assert reparsed == result
    assert reparsed.ai_suitability.level == "high"
    assert reparsed.recommended_solution.pattern == "llm_assisted_workflow"


def test_completed_response_requires_result_and_completion_timestamp() -> None:
    now = datetime.now(UTC)

    with pytest.raises(ValidationError):
        AssessmentResponse(
            assessment_id=uuid4(),
            status=AssessmentStatus.COMPLETED,
            input=AssessmentRequest(
                company_name="Example Bank",
                industry="Banking",
                business_problem="Manual review takes too long",
                desired_outcome="Reduce turnaround time",
            ),
            result=None,
            error=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
