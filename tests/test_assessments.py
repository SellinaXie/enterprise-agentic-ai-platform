"""Persisted assessment endpoint tests."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import APIConnectionError, OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_assessment_generator
from app.core.config import Settings
from app.db.models.assessment import AssessmentModel
from app.main import create_app
from app.models.assessment import AssessmentStatus
from app.schemas.assessment import AssessmentRequest, AssessmentResponse, AssessmentResult
from app.services.assessments import AssessmentGenerator
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
    """Inject a deterministic generator while retaining real persistence."""
    app.dependency_overrides[get_assessment_generator] = lambda: generator


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


def get_only_assessment(session_factory: sessionmaker[Session]) -> AssessmentModel:
    """Return the single row created by one isolated API test."""
    with session_factory() as session:
        return session.scalars(select(AssessmentModel)).one()


def test_create_assessment_persists_structured_result(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    expected_result = build_assessment_result()
    generator, openai_client = mock_openai_generator(expected_result)
    override_generator(app, generator)

    response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 200
    payload = response.json()
    assessment_id = UUID(payload["assessment_id"])
    parsed_response = AssessmentResponse.model_validate(payload)
    assert parsed_response.status == AssessmentStatus.COMPLETED
    assert parsed_response.input.company_name == VALID_REQUEST["company_name"]
    assert parsed_response.result == expected_result
    assert parsed_response.error is None
    assert parsed_response.created_at <= parsed_response.updated_at
    assert parsed_response.completed_at is not None

    persisted = get_only_assessment(session_factory)
    assert persisted.id == assessment_id
    assert persisted.status == AssessmentStatus.COMPLETED
    assert persisted.request_payload["company_name"] == VALID_REQUEST["company_name"]
    assert AssessmentResult.model_validate(persisted.result_payload) == expected_result

    call = openai_client.responses.parse.call_args
    assert call.kwargs["model"] == "gpt-4.1-mini"
    assert call.kwargs["text_format"] is AssessmentResult
    assert call.kwargs["store"] is False
    assert call.kwargs["input"][0]["role"] == "system"
    assert "Example Bank" in call.kwargs["input"][1]["content"]


def test_get_assessment_returns_persisted_state(
    app: FastAPI,
    client: TestClient,
) -> None:
    expected_result = build_assessment_result()
    generator, _ = mock_openai_generator(expected_result)
    override_generator(app, generator)
    created = client.post("/api/v1/assessments", json=VALID_REQUEST).json()

    response = client.get(f"/api/v1/assessments/{created['assessment_id']}")

    assert response.status_code == 200
    retrieved = AssessmentResponse.model_validate(response.json())
    assert retrieved.assessment_id == UUID(created["assessment_id"])
    assert retrieved.input == AssessmentRequest.model_validate(VALID_REQUEST)
    assert retrieved.result == expected_result
    assert retrieved.status == AssessmentStatus.COMPLETED


def test_get_unknown_assessment_returns_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/assessments/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "assessment_not_found",
            "message": "The requested assessment was not found.",
        }
    }


def test_get_invalid_assessment_id_returns_422(client: TestClient) -> None:
    response = client.get("/api/v1/assessments/not-a-uuid")

    assert response.status_code == 422


def test_create_assessment_rejects_blank_required_field(client: TestClient) -> None:
    response = client.post(
        "/api/v1/assessments",
        json={**VALID_REQUEST, "company_name": "   "},
    )

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


def test_create_assessment_without_api_key_persists_failure(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "openai_not_configured",
            "message": "AI assessments are unavailable because OPENAI_API_KEY is not configured.",
        }
    }
    persisted = get_only_assessment(session_factory)
    assert persisted.status == AssessmentStatus.FAILED
    assert persisted.result_payload is None
    assert persisted.error_code == "openai_not_configured"
    assert "OPENAI_API_KEY" in persisted.error_message

    retrieved_response = client.get(f"/api/v1/assessments/{persisted.id}")
    retrieved = AssessmentResponse.model_validate(retrieved_response.json())
    assert retrieved.status == AssessmentStatus.FAILED
    assert retrieved.result is None
    assert retrieved.error is not None
    assert retrieved.error.code == "openai_not_configured"


def test_provider_failure_returns_safe_error_and_persists_failure(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
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
    persisted = get_only_assessment(session_factory)
    assert persisted.status == AssessmentStatus.FAILED
    assert persisted.error_code == "llm_provider_error"


def test_invalid_model_output_returns_safe_error_and_persists_failure(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
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
    persisted = get_only_assessment(session_factory)
    assert persisted.status == AssessmentStatus.FAILED
    assert persisted.result_payload is None
    assert persisted.error_code == "invalid_llm_response"


def test_unexpected_generation_failure_is_safe_and_persisted(
    app: FastAPI,
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    generator = Mock()
    generator.generate.side_effect = RuntimeError("private provider detail")
    override_generator(app, cast(AssessmentGenerator, generator))

    response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "assessment_generation_error",
            "message": "AI assessment generation failed unexpectedly. Please try again.",
        }
    }
    persisted = get_only_assessment(session_factory)
    assert persisted.status == AssessmentStatus.FAILED
    assert persisted.error_code == "assessment_generation_error"
    assert "private provider detail" not in persisted.error_message


def test_missing_database_url_returns_controlled_error() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        APP_LOG_LEVEL="ERROR",
        DATABASE_URL=None,
        OPENAI_API_KEY=None,
    )
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_not_configured",
            "message": (
                "Assessment persistence is unavailable because DATABASE_URL is not configured."
            ),
        }
    }


def test_invalid_database_url_returns_controlled_error() -> None:
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        APP_LOG_LEVEL="ERROR",
        DATABASE_URL="not-a-valid-sqlalchemy-url",
        OPENAI_API_KEY=None,
    )
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.post("/api/v1/assessments", json=VALID_REQUEST)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "Assessment persistence is temporarily unavailable. Please try again.",
        }
    }
