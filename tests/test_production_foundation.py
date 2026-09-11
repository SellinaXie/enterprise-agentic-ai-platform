"""V8A production-boundary, readiness, correlation, and logging tests."""

from __future__ import annotations

import json
import logging
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, text

from app.api.dependencies import get_assessment_generator
from app.core.config import Settings
from app.core.logging import JsonFormatter
from app.db.session import get_engine
from app.main import create_app
from app.schemas.assessment import AssessmentResponse
from app.schemas.knowledge import KnowledgeDocumentCreate
from tests.factories import build_assessment_result
from tests.test_assessments import VALID_REQUEST


class StaticAssessmentGenerator:
    """Network-free provider substitute for correlation persistence."""

    def generate(self, _: object) -> object:
        return build_assessment_result()


def _production_settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "APP_ENV": "production",
        "APP_DEBUG": False,
        "DATABASE_URL": "postgresql+psycopg://app:strong-local-test@db/enterprise_ai",
        "OPENAI_API_KEY": "configured-through-secret-injection",
        "CORS_ALLOWED_ORIGINS": "https://app.example.invalid",
        "TRUSTED_HOSTS": "api.example.invalid",
    }
    values.update(updates)
    return Settings(**values)


@pytest.mark.parametrize(
    "updates",
    [
        {"DATABASE_URL": None},
        {"DATABASE_URL": "sqlite:///unsafe.db"},
        {"DATABASE_URL": "postgresql+psycopg://app:change-me@db/enterprise_ai"},
        {"OPENAI_API_KEY": None},
        {"OPENAI_API_KEY": "replace-with-openai-key"},
        {"APP_DEBUG": True},
        {"CORS_ALLOWED_ORIGINS": "*"},
        {"TRUSTED_HOSTS": "*"},
        {"LOG_EXCEPTION_TRACEBACKS": True},
    ],
)
def test_production_profile_rejects_unsafe_configuration(updates: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _production_settings(**updates)


def test_production_profile_can_explicitly_disable_unused_provider() -> None:
    settings = _production_settings(OPENAI_API_KEY=None, PROVIDER_REQUIRED=False)
    assert settings.provider_is_configured is False


def test_partial_pricing_configuration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, MODEL_INPUT_COST_PER_1M_TOKENS=1.0)


def test_readiness_reports_missing_dependencies_without_secrets() -> None:
    application = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            APP_LOG_LEVEL="ERROR",
            DATABASE_URL=None,
            OPENAI_API_KEY=None,
            PROVIDER_REQUIRED=False,
        )
    )
    with TestClient(application) as client:
        response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {
            "database": "not_ready",
            "schema": "not_ready",
            "configuration": "ready",
        },
    }


def test_readiness_accepts_connected_head_schema(
    database_url: str,
    engine: Engine,
) -> None:
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('20260910_0005')"))
    application = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            APP_LOG_LEVEL="ERROR",
            DATABASE_URL=database_url,
            OPENAI_API_KEY=None,
            PROVIDER_REQUIRED=False,
        )
    )

    with TestClient(application) as client:
        response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert get_engine.cache_info().currsize == 0


def test_request_id_is_accepted_generated_and_returned(client: TestClient) -> None:
    accepted = client.get("/health", headers={"X-Request-ID": "external-request_123"})
    rejected = client.get("/health", headers={"X-Request-ID": "unsafe value"})

    assert accepted.headers["x-request-id"] == "external-request_123"
    generated = rejected.headers["x-request-id"]
    assert UUID(generated).version == 4


def test_request_id_is_persisted_in_assessment_execution(
    app: FastAPI,
    client: TestClient,
) -> None:
    app.dependency_overrides[get_assessment_generator] = lambda: StaticAssessmentGenerator()
    response = client.post(
        "/api/v1/assessments",
        headers={"X-Request-ID": "assessment-correlation-1"},
        json=VALID_REQUEST,
    )

    parsed = AssessmentResponse.model_validate(response.json())
    assert response.status_code == 200
    assert parsed.execution is not None
    assert parsed.execution.request_id == "assessment-correlation-1"


def test_controlled_error_contains_request_id_without_configuration_details() -> None:
    application = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            APP_LOG_LEVEL="ERROR",
            DATABASE_URL=None,
            OPENAI_API_KEY=None,
            PROVIDER_REQUIRED=False,
        )
    )
    with TestClient(application) as client:
        response = client.get(
            f"/api/v1/assessments/{uuid4()}",
            headers={"X-Request-ID": "safe-error-id"},
        )

    assert response.status_code == 503
    assert response.json()["request_id"] == "safe-error-id"
    assert "DATABASE_URL" in response.json()["error"]["message"]
    assert "postgresql" not in response.text


def test_unexpected_error_is_sanitized() -> None:
    application = create_app(Settings(_env_file=None, APP_ENV="test", APP_LOG_LEVEL="ERROR"))

    @application.get("/synthetic-failure")
    def fail_safely() -> None:
        raise RuntimeError("private database path /tmp/private.db")

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/synthetic-failure", headers={"X-Request-ID": "unexpected-error-id"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_server_error",
            "message": "The request could not be completed.",
        },
        "request_id": "unexpected-error-id",
    }
    assert "/tmp/private.db" not in response.text


def test_json_content_length_guard_rejects_oversized_request() -> None:
    application = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            APP_LOG_LEVEL="ERROR",
            MAX_JSON_REQUEST_SIZE_KB=1,
        )
    )
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/assessments",
            content=b"x" * 1_025,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_cors_uses_explicit_allowlist() -> None:
    application = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            CORS_ALLOWED_ORIGINS="https://allowed.example.invalid",
        )
    )
    with TestClient(application) as client:
        allowed = client.options(
            "/health",
            headers={
                "Origin": "https://allowed.example.invalid",
                "Access-Control-Request-Method": "GET",
            },
        )
        denied = client.options(
            "/health",
            headers={
                "Origin": "https://denied.example.invalid",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://allowed.example.invalid"
    assert denied.status_code == 400


def test_json_logging_omits_sensitive_payload_fields() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord("test", logging.ERROR, __file__, 1, "safe_event", (), None)
    record.request_id = "log-request-id"
    record.assessment_id = "synthetic-assessment"
    record.prompt = "private prompt"
    record.api_key = "private key"
    record.embedding = [0.1, 0.2]

    payload = json.loads(formatter.format(record))

    assert payload["event"] == "safe_event"
    assert payload["request_id"] == "log-request-id"
    assert payload["assessment_id"] == "synthetic-assessment"
    assert "prompt" not in payload
    assert "api_key" not in payload
    assert "embedding" not in payload
    assert "private" not in json.dumps(payload)


def test_plain_text_metadata_is_bounded() -> None:
    with pytest.raises(ValidationError):
        KnowledgeDocumentCreate(
            title="Synthetic",
            content="Synthetic content",
            metadata={"oversized": "x" * 100_001},
        )
