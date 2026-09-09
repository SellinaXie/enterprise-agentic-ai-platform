"""Knowledge API tests with SQLite and deterministic provider doubles."""

from unittest.mock import Mock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_embeddings_service, get_retrieval_service
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.rag.retrieval import RetrievalService
from app.schemas.knowledge import KnowledgeDocumentCreate
from tests.knowledge_fixtures import DeterministicEmbeddingsService


def test_ingest_and_get_synthetic_document(
    app: FastAPI,
    client: TestClient,
    synthetic_knowledge_corpus: list[KnowledgeDocumentCreate],
) -> None:
    app.dependency_overrides[get_embeddings_service] = lambda: DeterministicEmbeddingsService(3)
    request = synthetic_knowledge_corpus[0]

    response = client.post("/api/v1/knowledge/documents", json=request.model_dump(mode="json"))

    assert response.status_code == 201
    created = response.json()
    assert created["document"]["title"] == request.title
    assert created["document"]["metadata"] == request.metadata
    assert created["chunk_count"] >= 1

    retrieved = client.get(f"/api/v1/knowledge/documents/{created['document']['document_id']}")
    assert retrieved.status_code == 200
    assert retrieved.json()["content"] == request.content


def test_search_endpoint_returns_typed_ranked_sources(
    app: FastAPI,
    client: TestClient,
) -> None:
    evidence = RetrievedEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic Compliance Workflow",
        content="Authorized compliance review is required.",
        similarity_score=0.93,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )
    retrieval = Mock(spec=RetrievalService)
    retrieval.search.return_value = [evidence]
    app.dependency_overrides[get_retrieval_service] = lambda: retrieval

    response = client.post(
        "/api/v1/knowledge/search",
        json={"query": "compliance review", "top_k": 3},
    )

    assert response.status_code == 200
    assert response.json()["results"] == [
        {
            "chunk_id": str(evidence.chunk_id),
            "document_id": str(evidence.document_id),
            "document_title": evidence.document_title,
            "content": evidence.content,
            "similarity_score": evidence.similarity_score,
            "source_type": "synthetic",
            "metadata": {"synthetic": True},
        }
    ]
    retrieval.search.assert_called_once_with(
        "compliance review",
        top_k=3,
        similarity_threshold=None,
        source_type=None,
        document_id=None,
    )


def test_unknown_knowledge_document_returns_404(
    app: FastAPI,
    client: TestClient,
) -> None:
    app.dependency_overrides[get_embeddings_service] = lambda: DeterministicEmbeddingsService(3)

    response = client.get(f"/api/v1/knowledge/documents/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "knowledge_document_not_found",
            "message": "The requested knowledge document was not found.",
        }
    }


def test_ingestion_without_api_key_returns_safe_error(
    client: TestClient,
    synthetic_knowledge_corpus: list[KnowledgeDocumentCreate],
) -> None:
    response = client.post(
        "/api/v1/knowledge/documents",
        json=synthetic_knowledge_corpus[0].model_dump(mode="json"),
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "embedding_not_configured",
            "message": (
                "Knowledge embeddings are unavailable because OPENAI_API_KEY is not configured."
            ),
        }
    }
