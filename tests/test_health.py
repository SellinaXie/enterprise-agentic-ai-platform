"""Health endpoint tests."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_check(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.8.0rc1"}
    assert response.headers["x-request-id"]


def test_health_does_not_require_database_configuration() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            APP_LOG_LEVEL="ERROR",
            DATABASE_URL=None,
            OPENAI_API_KEY=None,
        )
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.8.0rc1"}
