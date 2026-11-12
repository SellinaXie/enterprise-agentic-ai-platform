"""Deployment settings must never inherit the local authentication bypass."""

import pytest
from pydantic import ValidationError

from app.core.vercel import vercel_settings


@pytest.fixture
def vercel_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("DATABASE_URL", "postgresql://testuser:secure-password@db.internal/app")
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key")
    monkeypatch.setenv("AUTH_JWT_VERIFICATION_KEY", "a" * 40)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "https://issuer.test/")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "enterprise-ai")
    monkeypatch.setenv("TRUSTED_HOSTS", "app.example.com")
    monkeypatch.setenv("VERCEL_URL", "project-preview.vercel.app")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "project.vercel.app")


def test_vercel_enforces_production_auth(vercel_environment: None) -> None:
    settings = vercel_settings()
    assert settings.environment == "production"
    assert settings.auth_enabled is True
    assert settings.debug is False
    assert settings.parsed_trusted_hosts == [
        "app.example.com", "project-preview.vercel.app", "project.vercel.app"
    ]


def test_vercel_rejects_missing_database(
    vercel_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(ValidationError, match="DATABASE_URL is required"):
        vercel_settings()


def test_vercel_rejects_placeholder_credentials(
    vercel_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTH_JWT_VERIFICATION_KEY", "replace-with-at-least-32-random-characters")
    with pytest.raises(ValidationError, match="unsafe for production"):
        vercel_settings()


def test_vercel_uses_defaults_for_empty_optional_settings(
    vercel_environment: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RAG_ENABLED", "")
    monkeypatch.setenv("AUTH_JWT_ALGORITHM", "")
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "")
    settings = vercel_settings()
    assert settings.rag_enabled is False
    assert settings.auth_jwt_algorithm == "HS256"
    assert settings.database_connect_timeout_seconds == 5
