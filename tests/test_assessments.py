"""Assessment endpoint tests."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from uuid import UUID

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import APIConnectionError, OpenAI

from app.api.dependencies import get_assessment_service
from app.schemas.assessment import AssessmentResponse, AssessmentResult
from app.services.assessments import AssessmentGenerator, AssessmentService
from app.services.llm import OpenAIAssessmentGenerator
from tests.factories import build_assessment_result

VALID_REQUEST = {
    "company_name": "Example Bank",
    "organization_description": "A regional retail and commercial bank.",
    "industry": "Banking",
    "business_problem": "Manual loan review takes too long",
    "current_process": "Analysts manually gather documents and assess risk",
    "pain_points": ["Repeated document collection", "Inconsistent review summaries"],
    "desired_outcome": "Reduce processing time while preserving compliance",
    "constraints": ["Final credit decisions require human approval"],
}


def override_generator(app: FastAPI, generator: AssessmentGenerator) -> None:
    """Inject a deterministic generator at the API composition boundary."""
    app.dependency_overrides[get_assessment_service] = lambda: AssessmentService(generator)


def mock_openai_generator(
    parsed_result: AssessmentResult | dict[str, str] | None,
) -> tuple[OpenAIAssessmentGenerator, Mock]:
    """Build an OpenAI generator around a non-networked mock client."""
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(output_parsed=parsed_result)
    generator = OpenAIAssessmentGenerator(
        model="gpt-4.1-mini",
        client_provider=lambda: cast(OpenAI, client),
    )
    return generator, client


def test_create_assessment_returns_structured_result(
    app: FastAPI,
    client: TestClient,
) -> None:
    expected_result = build_assessment_result()
    generator, openai_client = mock_openai_generator(expected_result)
    override_generator(app, generator)

    response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 200
    payload = response.json()
    assert UUID(payload["assessment_id"])
    parsed_response = AssessmentResponse.model_validate(payload)
    assert parsed_response.status == "completed"
    assert parsed_response.result == expected_result

    call = openai_client.responses.parse.call_args
    assert call.kwargs["model"] == "gpt-4.1-mini"
    assert call.kwargs["text_format"] is AssessmentResult
    assert call.kwargs["store"] is False
    assert call.kwargs["input"][0]["role"] == "system"
    assert "Example Bank" in call.kwargs["input"][1]["content"]


def test_create_assessment_rejects_blank_required_field(client: TestClient) -> None:
    invalid_request = {**VALID_REQUEST, "company_name": "   "}

    response = client.post("/api/v1/assessments", json=invalid_request)

    assert response.status_code == 422


def test_create_assessment_allows_optional_context_to_be_omitted(
    app: FastAPI,
    client: TestClient,
) -> None:
    generator, _ = mock_openai_generator(build_assessment_result())
    override_generator(app, generator)
    minimal_request = {
        "company_name": "Example Manufacturer",
        "industry": "Manufacturing",
        "business_problem": "Quality reports take too long to prepare",
        "desired_outcome": "Shorten reporting lead time",
    }

    response = client.post("/api/v1/assessments", json=minimal_request)

    assert response.status_code == 200


def test_create_assessment_without_api_key_returns_controlled_error(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "openai_not_configured",
            "message": ("AI assessments are unavailable because OPENAI_API_KEY is not configured."),
        }
    }


def test_provider_failure_returns_safe_error(app: FastAPI, client: TestClient) -> None:
    openai_client = Mock()
    openai_client.responses.parse.side_effect = APIConnectionError(
        request=httpx.Request("POST", "https://api.openai.com/v1/responses")
    )
    generator = OpenAIAssessmentGenerator(
        model="gpt-4.1-mini",
        client_provider=lambda: cast(OpenAI, openai_client),
    )
    override_generator(app, generator)

    response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "llm_provider_error",
            "message": "AI assessment generation is temporarily unavailable. Please try again.",
        }
    }


def test_invalid_model_output_returns_controlled_error(
    app: FastAPI,
    client: TestClient,
) -> None:
    generator, _ = mock_openai_generator({"executive_summary": "Incomplete output"})
    override_generator(app, generator)

    response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "invalid_llm_response",
            "message": "The AI service returned an invalid assessment. Please try again.",
        }
    }
