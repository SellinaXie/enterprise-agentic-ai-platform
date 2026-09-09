"""Shared pytest fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.db.models import AssessmentModel  # noqa: F401
from app.db.session import get_engine, get_session_factory
from app.main import create_app


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """Return a unique SQLite URL for one isolated test."""
    return f"sqlite+pysqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def settings(database_url: str) -> Settings:
    """Create isolated, keyless application settings."""
    return Settings(
        _env_file=None,
        APP_ENV="test",
        APP_LOG_LEVEL="ERROR",
        DATABASE_URL=database_url,
        OPENAI_API_KEY=None,
    )


@pytest.fixture
def engine(database_url: str) -> Iterator[Engine]:
    """Create the isolated database schema for a test and dispose it afterward."""
    database_engine = get_engine(database_url)
    Base.metadata.create_all(database_engine)
    yield database_engine
    database_engine.dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()


@pytest.fixture
def session_factory(
    database_url: str,
    engine: Engine,
) -> sessionmaker[Session]:
    """Return the same cached factory used by FastAPI dependencies."""
    del engine
    return get_session_factory(database_url)


@pytest.fixture
def db_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a direct session for repository assertions."""
    with session_factory() as session:
        yield session


@pytest.fixture
def app(settings: Settings, engine: Engine) -> FastAPI:
    """Create an application backed by the isolated test database."""
    del engine
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Return a test client without making external API calls."""
    with TestClient(app) as test_client:
        yield test_client
