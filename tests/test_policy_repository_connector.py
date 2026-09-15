"""Network-free tests for the single V8D enterprise connector."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_policy_repository_connector
from app.connectors.policy_repository import PolicyRepositoryConnector
from app.core.config import Settings
from app.core.exceptions import ConnectorUnavailableError, InvalidConnectorResponseError
from app.main import create_app
from app.models.knowledge import KnowledgeSourceType


def _connector(
    handler: object,
    *,
    knowledge: Mock | None = None,
    graph: Mock | None = None,
    max_response_bytes: int = 100_000,
) -> tuple[PolicyRepositoryConnector, Mock]:
    service = knowledge or Mock()
    if knowledge is None:
        service.ingest.return_value = SimpleNamespace(
            document=SimpleNamespace(document_id=uuid4()), duplicate=False
        )
    client = httpx.Client(
        base_url="https://policies.example.test",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )
    return (
        PolicyRepositoryConnector(
            base_url="https://policies.example.test",
            token="synthetic-token",
            documents_path="/v1/documents",
            knowledge=service,
            graph=graph,
            timeout_seconds=2,
            max_documents=10,
            max_response_bytes=max_response_bytes,
            client=client,
        ),
        service,
    )


def test_policy_sync_reuses_ingestion_and_preserves_provenance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "10"
        return httpx.Response(
            200,
            json={
                "documents": [
                    {
                        "external_id": "POL-001",
                        "title": "Synthetic Data Handling Policy",
                        "content": "PII access requires approval and an audit record.",
                        "source_uri": "https://policies.example.test/POL-001",
                        "updated_at": "2026-09-01T12:00:00Z",
                        "metadata": {"classification": "internal"},
                    }
                ]
            },
        )

    connector, knowledge = _connector(handler)
    result = connector.sync()

    assert result.fetched == result.ingested == 1
    request = knowledge.ingest.call_args.args[0]
    assert request.source_type == KnowledgeSourceType.POLICY
    assert request.external_id == "POL-001"
    assert request.metadata["connector"] == {
        "type": "policy_repository",
        "repository_host": "policies.example.test",
        "external_updated_at": "2026-09-01T12:00:00+00:00",
    }
    assert knowledge.ingest.call_args.kwargs == {"deduplicate": True}


def test_policy_sync_degrades_graph_enrichment_without_losing_document() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "documents": [{"external_id": "POL-002", "title": "Policy", "content": "Content"}]
            },
        )

    graph = Mock()
    graph.enrich.side_effect = RuntimeError("synthetic graph failure")
    connector, _ = _connector(handler, graph=graph)

    result = connector.sync(enrich_graph=True)

    assert result.ingested == 1
    assert result.graph_enriched == 0
    assert result.graph_failed == 1


def test_policy_sync_rejects_upstream_failure_and_oversized_payload() -> None:
    unavailable, _ = _connector(lambda _: httpx.Response(503))
    oversized, _ = _connector(
        lambda _: httpx.Response(
            200,
            json={"documents": [{"external_id": "1", "title": "T", "content": "long"}]},
        ),
        max_response_bytes=1,
    )

    with pytest.raises(ConnectorUnavailableError):
        unavailable.sync()
    with pytest.raises(InvalidConnectorResponseError):
        oversized.sync()


class ConnectorStub:
    def sync(self, *, enrich_graph: bool = False) -> object:
        assert enrich_graph is False
        return {
            "fetched": 1,
            "ingested": 1,
            "duplicates": 0,
            "graph_enriched": 0,
            "graph_failed": 0,
            "document_ids": [uuid4()],
        }


def test_admin_connector_api_exposes_only_bounded_sync_result() -> None:
    settings = Settings(_env_file=None, APP_ENV="test", PROVIDER_REQUIRED=False)
    application = create_app(settings)
    application.dependency_overrides[get_policy_repository_connector] = ConnectorStub

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/connectors/policy-repository/sync",
            json={"enrich_graph": False},
        )

    assert response.status_code == 200
    assert response.json()["fetched"] == 1
    assert set(response.json()) == {
        "fetched",
        "ingested",
        "duplicates",
        "graph_enriched",
        "graph_failed",
        "document_ids",
    }


def test_disabled_connector_fails_before_provider_or_database_work() -> None:
    settings = Settings(_env_file=None, APP_ENV="test", PROVIDER_REQUIRED=False)
    application = create_app(settings)

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/connectors/policy-repository/sync",
            json={"enrich_graph": False},
        )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "connector_not_configured"


def test_policy_sync_requires_admin_role_when_authentication_is_enabled() -> None:
    secret = "synthetic-test-signing-key-with-more-than-32-characters"
    issuer = "https://identity.test.invalid/"
    audience = "enterprise-agentic-ai-platform"
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        PROVIDER_REQUIRED=False,
        AUTH_ENABLED=True,
        AUTH_JWT_SECRET=secret,
        AUTH_JWT_ISSUER=issuer,
        AUTH_JWT_AUDIENCE=audience,
    )
    token = jwt.encode(
        {
            "sub": "synthetic-analyst",
            "iss": issuer,
            "aud": audience,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "roles": ["analyst"],
        },
        secret,
        algorithm="HS256",
    )
    application = create_app(settings)
    application.dependency_overrides[get_policy_repository_connector] = ConnectorStub

    with TestClient(application) as client:
        response = client.post(
            "/api/v1/connectors/policy-repository/sync",
            json={"enrich_graph": False},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
