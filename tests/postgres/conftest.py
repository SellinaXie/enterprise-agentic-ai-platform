"""Fixtures and safety guards for live PostgreSQL integration tests."""

import os
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import Settings
from app.db.session import get_engine, get_session_factory
from app.schemas.assessment import AssessmentRequest, AssessmentResult
from tests.factories import build_assessment_result

SYNTHETIC_REQUEST_PAYLOAD = {
    "company_name": "Example Bank",
    "organization_description": "A synthetic regional retail and commercial bank.",
    "industry": "Banking",
    "business_problem": "Manual loan review takes too long",
    "current_process": "Analysts manually gather documents and assess risk",
    "pain_points": ["Repeated document collection", "Inconsistent review summaries"],
    "desired_outcome": "Reduce processing time while preserving compliance",
    "constraints": ["Final credit decisions require human approval"],
}


def _database_identity(url: URL) -> tuple[str, int, str]:
    """Return connection identity without credentials."""
    return (
        (url.host or "localhost").lower(),
        url.port or 5432,
        (url.database or "").lower(),
    )


def _validated_test_database_url() -> str:
    """Load and validate a URL before destructive test-database operations."""
    raw_url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not raw_url:
        pytest.skip(
            "TEST_DATABASE_URL is not configured; live PostgreSQL tests were not run",
            allow_module_level=True,
        )

    try:
        test_url = make_url(raw_url)
    except ArgumentError as exc:
        raise pytest.UsageError("TEST_DATABASE_URL is not a valid SQLAlchemy URL") from exc

    if test_url.get_backend_name() != "postgresql":
        raise pytest.UsageError("TEST_DATABASE_URL must use PostgreSQL")

    database_name = (test_url.database or "").lower()
    if not database_name or "test" not in database_name:
        raise pytest.UsageError("TEST_DATABASE_URL database name must contain 'test'")
    if database_name in {"postgres", "template0", "template1"}:
        raise pytest.UsageError("TEST_DATABASE_URL cannot use a PostgreSQL maintenance database")
    if "prod" in database_name or "production" in database_name:
        raise pytest.UsageError("TEST_DATABASE_URL cannot use a production-looking database name")

    configured_database_url = Settings().database_url
    production_url = (
        configured_database_url.get_secret_value().strip()
        if configured_database_url is not None
        else ""
    )
    if production_url:
        try:
            application_url = make_url(production_url)
        except ArgumentError:
            application_url = None
        if (
            application_url is not None
            and application_url.get_backend_name() == "postgresql"
            and _database_identity(application_url) == _database_identity(test_url)
        ):
            raise pytest.UsageError("TEST_DATABASE_URL must not point to DATABASE_URL")

    return raw_url


def _alembic_config() -> Config:
    project_root = Path(__file__).resolve().parents[2]
    return Config(str(project_root / "alembic.ini"))


@pytest.fixture(scope="session")
def postgres_database_url() -> str:
    """Return a safety-checked dedicated PostgreSQL test URL."""
    return _validated_test_database_url()


@pytest.fixture
def synthetic_assessment_request() -> AssessmentRequest:
    """Return local synthetic input without loading an external dataset."""
    return AssessmentRequest.model_validate(SYNTHETIC_REQUEST_PAYLOAD)


@pytest.fixture
def synthetic_assessment_result() -> AssessmentResult:
    """Return a deterministic synthetic result without calling OpenAI."""
    return build_assessment_result()


@pytest.fixture(scope="session")
def postgres_engine(postgres_database_url: str) -> Iterator[Engine]:
    """Reset the complete schema and provide a connected PostgreSQL engine."""
    probe_engine = create_engine(postgres_database_url, pool_pre_ping=True)
    try:
        with probe_engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            connected_database = connection.execute(text("SELECT current_database()")).scalar_one()
            expected_database = make_url(postgres_database_url).database
            if (
                expected_database is None
                or connected_database.lower() != expected_database.lower()
                or "test" not in connected_database.lower()
                or "prod" in connected_database.lower()
            ):
                raise pytest.UsageError(
                    "Connected PostgreSQL database did not pass the dedicated-test guard"
                )
    finally:
        probe_engine.dispose()

    with patch.dict(os.environ, {"DATABASE_URL": postgres_database_url}):
        command.downgrade(_alembic_config(), "base")

        migration_engine = create_engine(postgres_database_url, pool_pre_ping=True)
        try:
            with migration_engine.connect() as connection:
                downgrade_revision = MigrationContext.configure(connection).get_current_revision()
                assessment_table_removed = not inspect(connection).has_table("assessments")
                knowledge_tables_removed = not inspect(connection).has_table(
                    "knowledge_documents"
                ) and not inspect(connection).has_table("knowledge_chunks")
        finally:
            migration_engine.dispose()

        command.upgrade(_alembic_config(), "head")

        migration_engine = create_engine(postgres_database_url, pool_pre_ping=True)
        try:
            with migration_engine.connect() as connection:
                upgrade_revision = MigrationContext.configure(connection).get_current_revision()
                assessment_table_created = inspect(connection).has_table("assessments")
                knowledge_tables_created = inspect(connection).has_table(
                    "knowledge_documents"
                ) and inspect(connection).has_table("knowledge_chunks")
        finally:
            migration_engine.dispose()

    assert downgrade_revision is None
    assert assessment_table_removed
    assert knowledge_tables_removed
    assert upgrade_revision == "20260909_0003"
    assert assessment_table_created
    assert knowledge_tables_created

    get_session_factory.cache_clear()
    get_engine.cache_clear()
    database_engine = get_engine(postgres_database_url)
    try:
        yield database_engine
    finally:
        with database_engine.begin() as connection:
            connection.execute(text("DELETE FROM assessments"))
            connection.execute(text("DELETE FROM knowledge_chunks"))
            connection.execute(text("DELETE FROM knowledge_documents"))
        database_engine.dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()


@pytest.fixture(scope="session")
def postgres_session_factory(
    postgres_database_url: str,
    postgres_engine: Engine,
) -> sessionmaker[Session]:
    """Return the application session factory bound to the test database."""
    del postgres_engine
    return get_session_factory(postgres_database_url)


@pytest.fixture(autouse=True)
def clean_postgres_test_data(postgres_engine: Engine) -> Iterator[None]:
    """Keep every PostgreSQL test independent of execution order."""
    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM assessments"))
        connection.execute(text("DELETE FROM knowledge_chunks"))
        connection.execute(text("DELETE FROM knowledge_documents"))
    yield
    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM assessments"))
        connection.execute(text("DELETE FROM knowledge_chunks"))
        connection.execute(text("DELETE FROM knowledge_documents"))
