"""Alembic history and PostgreSQL offline-DDL verification."""

from io import StringIO
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch

from alembic import command


def alembic_config(output_buffer: StringIO | None = None) -> Config:
    root = Path(__file__).resolve().parents[1]
    return Config(str(root / "alembic.ini"), output_buffer=output_buffer)


def test_alembic_has_one_linear_head() -> None:
    script = ScriptDirectory.from_config(alembic_config())

    assert script.get_heads() == ["20260909_0001"]
    assert script.get_base() == "20260909_0001"


def test_initial_migration_renders_postgresql_schema(monkeypatch: MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://migration_test:placeholder@localhost/migration_test",
    )

    command.upgrade(alembic_config(output), "head", sql=True)

    sql = output.getvalue()
    assert "CREATE TABLE assessments" in sql
    assert "JSONB" in sql
    assert "UUID" in sql
    assert "ix_assessments_status" in sql
    assert "ix_assessments_created_at" in sql


def test_initial_migration_renders_downgrade(monkeypatch: MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://migration_test:placeholder@localhost/migration_test",
    )

    command.downgrade(alembic_config(output), "20260909_0001:base", sql=True)

    sql = output.getvalue()
    assert "DROP INDEX ix_assessments_status" in sql
    assert "DROP INDEX ix_assessments_created_at" in sql
    assert "DROP TABLE assessments" in sql
