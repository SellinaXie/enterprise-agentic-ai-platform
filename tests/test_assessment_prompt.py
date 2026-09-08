"""Assessment context and prompt construction tests."""

import json

from app.schemas.assessment import AssessmentRequest
from app.services.assessment_prompt import (
    SYSTEM_INSTRUCTIONS,
    build_assessment_context,
    build_assessment_prompt,
)


def test_context_contains_only_supplied_fields() -> None:
    request = AssessmentRequest(
        company_name="Example Manufacturer",
        industry="Manufacturing",
        business_problem="Quality reports are slow",
        desired_outcome="Shorten reporting lead time",
    )

    context = json.loads(build_assessment_context(request))

    assert context == {
        "business_problem": "Quality reports are slow",
        "company_name": "Example Manufacturer",
        "desired_outcome": "Shorten reporting lead time",
        "industry": "Manufacturing",
    }


def test_prompt_is_deterministic_and_marks_context_as_untrusted() -> None:
    request = AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Manual review is slow",
        pain_points=["Duplicate data entry"],
        desired_outcome="Reduce turnaround time",
        additional_context="No baseline metrics are available.",
    )

    first_prompt = build_assessment_prompt(request)
    second_prompt = build_assessment_prompt(request)

    assert first_prompt == second_prompt
    assert "untrusted data" in first_prompt.system
    assert "Do not invent company-specific facts" in first_prompt.system
    assert "simplest reliable approach" in first_prompt.system
    assert "BEGIN_ASSESSMENT_CONTEXT" in first_prompt.user
    assert '"pain_points": [' in first_prompt.user
    assert first_prompt.system == SYSTEM_INSTRUCTIONS
