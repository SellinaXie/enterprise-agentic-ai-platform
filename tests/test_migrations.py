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

    assert script.get_heads() == ["20260910_0005"]
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
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE TABLE knowledge_documents" in sql
    assert "CREATE TABLE knowledge_chunks" in sql
    assert "VECTOR(1536)" in sql
    assert "USING hnsw" in sql
    assert "vector_cosine_ops" in sql
    assert "ADD COLUMN execution_metadata JSONB" in sql
    assert "CREATE TABLE knowledge_entities" in sql
    assert "CREATE TABLE knowledge_entity_mentions" in sql
    assert "CREATE TABLE knowledge_relationships" in sql
    assert "knowledge_relationships_no_self_edge" in sql
    assert "CREATE TABLE assessment_runtime_states" in sql
    assert "CREATE TABLE human_review_events" in sql
    assert "pending_review" in sql
    assert "DROP CONSTRAINT ck_assessments_assessment_status_values" in sql
    assert "ADD CONSTRAINT ck_assessments_assessment_status_values" in sql
    assert "ck_assessments_ck_assessments_assessment_status_values" not in sql


def test_v7c_migration_renders_postgresql_downgrade(monkeypatch: MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://migration_test:placeholder@localhost/migration_test",
    )

    command.downgrade(alembic_config(output), "20260910_0005:20260910_0004", sql=True)

    sql = output.getvalue()
    assert "DROP TABLE human_review_events" in sql
    assert "DROP TABLE assessment_runtime_states" in sql
    assert "DROP CONSTRAINT ck_assessments_assessment_status_values" in sql
    assert "ADD CONSTRAINT ck_assessments_assessment_status_values" in sql
    assert "ck_assessments_ck_assessments_assessment_status_values" not in sql


def test_v6_migration_renders_postgresql_downgrade(monkeypatch: MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://migration_test:placeholder@localhost/migration_test",
    )

    command.downgrade(alembic_config(output), "20260910_0004:20260909_0003", sql=True)

    sql = output.getvalue()
    assert "DROP TABLE knowledge_relationships" in sql
    assert "DROP TABLE knowledge_entity_mentions" in sql
    assert "DROP TABLE knowledge_entities" in sql


def test_v4_migration_renders_postgresql_downgrade(monkeypatch: MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://migration_test:placeholder@localhost/migration_test",
    )

    command.downgrade(alembic_config(output), "20260909_0003:20260909_0002", sql=True)

    assert "DROP COLUMN execution_metadata" in output.getvalue()


def test_v3_migration_renders_postgresql_downgrade(monkeypatch: MonkeyPatch) -> None:
    output = StringIO()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://migration_test:placeholder@localhost/migration_test",
    )

    command.downgrade(alembic_config(output), "20260909_0002:20260909_0001", sql=True)

    sql = output.getvalue()
    assert "DROP TABLE knowledge_chunks" in sql
    assert "DROP TABLE knowledge_documents" in sql
    assert "DROP EXTENSION" not in sql


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
