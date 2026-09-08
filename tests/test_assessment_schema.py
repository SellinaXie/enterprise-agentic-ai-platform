"""Structured assessment schema smoke tests."""

from app.schemas.assessment import AssessmentResult
from tests.factories import build_assessment_result


def test_structured_assessment_round_trips_through_pydantic() -> None:
    result = build_assessment_result()

    reparsed = AssessmentResult.model_validate_json(result.model_dump_json())

    assert reparsed == result
    assert reparsed.ai_suitability.level == "high"
    assert reparsed.recommended_solution.pattern == "llm_assisted_workflow"
