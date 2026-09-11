"""Unit tests for destructive PostgreSQL integration-test guards."""

import pytest

from scripts.postgres_probe import validated_test_database_url
from tests.postgres.conftest import _validated_test_database_url


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///enterprise_ai_test.db",
        "postgresql+psycopg://user:password@localhost/postgres",
        "postgresql+psycopg://user:password@localhost/enterprise_ai",
        "postgresql+psycopg://user:password@localhost/enterprise_ai_production_test",
    ],
)
def test_test_database_guard_rejects_unsafe_targets(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(pytest.UsageError):
        _validated_test_database_url()


def test_test_database_guard_rejects_application_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+psycopg://user:password@localhost/enterprise_ai_test"
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)
    monkeypatch.setenv("DATABASE_URL", database_url)

    with pytest.raises(pytest.UsageError):
        _validated_test_database_url()


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///enterprise_ai_test.db",
        "postgresql+psycopg://user:password@localhost/postgres",
        "postgresql+psycopg://user:password@localhost/enterprise_ai",
        "postgresql+psycopg://user:password@localhost/enterprise_ai_production_test",
    ],
)
def test_ci_probe_rejects_unsafe_targets(database_url: str) -> None:
    with pytest.raises(ValueError):
        validated_test_database_url({"TEST_DATABASE_URL": database_url})


def test_ci_probe_rejects_application_database() -> None:
    database_url = "postgresql+psycopg://user:password@localhost/enterprise_ai_test"

    with pytest.raises(ValueError):
        validated_test_database_url(
            {"TEST_DATABASE_URL": database_url, "DATABASE_URL": database_url}
        )


def test_ci_probe_accepts_dedicated_test_database() -> None:
    database_url = "postgresql+psycopg://user:password@localhost/enterprise_ai_test"

    assert (
        validated_test_database_url(
            {
                "TEST_DATABASE_URL": database_url,
                "DATABASE_URL": "postgresql+psycopg://user:password@localhost/enterprise_ai",
            }
        )
        == database_url
    )
