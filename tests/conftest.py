"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    """Create an application with isolated, keyless test settings."""
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        APP_LOG_LEVEL="ERROR",
        OPENAI_API_KEY=None,
    )
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Return a test client without making external API calls."""
    with TestClient(app) as test_client:
        yield test_client
