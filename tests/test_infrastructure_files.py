"""Static V8A infrastructure-contract tests that do not require a Docker daemon."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_container_is_python_312_non_root_and_health_checked() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "FROM python:3.12.12-slim-bookworm AS base" in dockerfile
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert 'CMD ["python", "-m", "app.server"]' in dockerfile
    assert 'os.getenv(\\"PORT\\", \\"8000\\")' in dockerfile
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
    assert "python scripts/postgres_probe.py" in workflow
    assert 'pytest -m "not postgres"' in workflow
    assert "python -m app.evaluation.runner --all" in workflow
    assert "python -m app.evaluation.assessment.runner --all" in workflow
    assert "docker build --target runtime" in workflow
    assert "docker compose up --build --detach postgres migrate api frontend" in workflow
    assert "npm run typecheck" in workflow
    assert "npm test" in workflow
    assert "npm run build" in workflow
    assert 'PROVIDER_REQUIRED: "false"' not in workflow.split("jobs:", maxsplit=1)[0]
    assert "continue-on-error" not in workflow


def test_frontend_container_is_non_root_and_compose_connected() -> None:
    dockerfile = (ROOT / "frontend/Dockerfile").read_text()
    compose = (ROOT / "compose.yaml").read_text()

    assert "FROM node:24.21.0-bookworm-slim" in dockerfile
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "process.env.PORT || '3000'" in dockerfile
    assert 'CMD ["node", "server.js"]' in dockerfile
    assert "ARG API_INTERNAL_URL" in dockerfile
    assert "API_INTERNAL_URL: http://api:8000" in compose
    assert "frontend:" in compose
    assert "context: ./frontend" in compose
    assert "FRONTEND_PORT" in compose
    assert "condition: service_healthy" in compose


def test_render_blueprint_connects_api_and_managed_postgres() -> None:
    blueprint = (ROOT / "render.yaml").read_text()

    assert "enterprise-ai-api" in blueprint
    assert "enterprise-ai-postgres" in blueprint
    assert "preDeployCommand: alembic upgrade head" in blueprint
    assert blueprint.count("autoDeployTrigger: checksPass") == 1
    assert "property: connectionString" in blueprint
    assert 'postgresMajorVersion: "16"' in blueprint
    assert "ipAllowList: []" in blueprint
    assert "AUTH_JWKS_URL" in blueprint
    assert "OPENAI_API_KEY" in blueprint
    assert "sync: false" in blueprint
    assert "https://demo.sellinaxie.com,https://app.sellinaxie.com" in blueprint
    assert "*" not in blueprint


def test_vercel_contract_uses_frontend_workspace_and_server_side_api_proxy() -> None:
    vercel = (ROOT / "frontend/vercel.json").read_text()
    next_config = (ROOT / "frontend/next.config.ts").read_text()
    production_example = (ROOT / "frontend/production.env.example").read_text()

    assert '"framework": "nextjs"' in vercel
    assert '"installCommand": "npm ci"' in vercel
    assert '"buildCommand": "npm run build"' in vercel
    assert 'source: "/backend/:path*"' in next_config
    assert "API_INTERNAL_URL" in next_config
    assert "NEXT_PUBLIC_API_BASE_URL=/backend" in production_example
    assert "NEXT_PUBLIC_APP_URL=https://app.sellinaxie.com" in production_example


def test_production_deploy_is_manual_protected_and_secret_backed() -> None:
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "environment: production" in workflow
    assert "secrets.RENDER_DEPLOY_HOOK_URL" in workflow
    assert "secrets.DEPLOYMENT_HEALTH_URL" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow


def test_database_recovery_wrappers_require_explicit_environment_inputs() -> None:
    backup = (ROOT / "scripts/backup_postgres.sh").read_text()
    restore = (ROOT / "scripts/restore_postgres.sh").read_text()

    assert "BACKUP_DATABASE_URL" in backup
    assert "pg_restore --list" in backup
    assert 'ALLOW_DATABASE_RESTORE:-}" != "true"' in restore
    assert "RESTORE_DATABASE_URL" in restore
    assert "--exit-on-error" in restore
    assert "--clean" not in restore
