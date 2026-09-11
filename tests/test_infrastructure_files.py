"""Static V8A infrastructure-contract tests that do not require a Docker daemon."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_container_is_python_312_non_root_and_health_checked() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "FROM python:3.12.12-slim-bookworm AS base" in dockerfile
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert '"app.main:app"' in dockerfile
    assert "--reload" not in dockerfile
    assert "COPY .env" not in dockerfile


def test_compose_separates_application_test_database_and_migrations() -> None:
    compose = (ROOT / "compose.yaml").read_text()

    assert "pgvector/pgvector:0.8.6-pg16-bookworm" in compose
    assert "POSTGRES_TEST_DB" in compose
    assert "TEST_DATABASE_URL" in compose
    assert "condition: service_healthy" in compose
    assert 'command: ["alembic", "upgrade", "head"]' in compose
    assert "service_completed_successfully" in compose


def test_docker_context_keeps_runtime_source_and_migrations() -> None:
    ignored = {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }

    assert ".env" in ignored
    assert ".git" in ignored
    assert "outputs" in ignored
    assert "app" not in ignored
    assert "alembic" not in ignored


def test_ci_requires_real_postgres_regressions_and_container_smoke() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()

    assert "push:" in workflow
    assert "pull_request:" in workflow
    assert "pytest -m postgres" in workflow
    assert 'pytest -m "not postgres"' in workflow
    assert "python -m app.evaluation.runner --all" in workflow
    assert "python -m app.evaluation.assessment.runner --all" in workflow
    assert "docker build --target runtime" in workflow
    assert "docker compose up --build --detach postgres migrate api" in workflow
    assert "continue-on-error" not in workflow
