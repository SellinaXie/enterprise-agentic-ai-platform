"""Multipart, persistence, deduplication, retrieval, and graph integration tests."""

import asyncio
import json
from io import BytesIO
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.agents.multi_agent_models import MultiAgentName
from app.api.dependencies import (
    get_embeddings_service,
    get_file_ingestion_service,
    get_graph_enrichment_service,
)
from app.core.exceptions import KnowledgeGraphExtractionError
from app.ingestion.parsers import PDFDocumentParser
from app.ingestion.router import DocumentParserRouter
from app.ingestion.service import FileIngestionService
from app.knowledge_graph.enrichment import KnowledgeGraphEnrichmentService
from app.knowledge_graph.retrieval import GraphRetrievalService
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.models.knowledge_graph import KnowledgeEntityType, KnowledgeRelationshipType
from app.rag.ingestion import KnowledgeIngestionService
from app.rag.retrieval import RetrievalService
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.repositories.knowledge_graph import KnowledgeGraphRepository
from app.schemas.knowledge_graph import (
    EntityExtractionResult,
    ExtractedEntity,
    ExtractedRelationship,
    RelationshipExtractionResult,
)
from app.tools.knowledge import build_knowledge_tool_registry
from app.tools.permissions import AgentToolPermissions
from tests.file_fixtures import build_docx, build_pdf
from tests.knowledge_fixtures import DeterministicEmbeddingsService

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@pytest.mark.parametrize(
    ("filename", "mime_type", "content", "expected_parser"),
    [
        (
            "policy.pdf",
            "application/pdf",
            build_pdf(
                "Synthetic PDF policy requires documented human approval for every material "
                "recommendation and retains evidence for audit review."
            ),
            "pypdf",
        ),
        ("manual.docx", DOCX_MIME, build_docx(), "python-docx"),
        ("notes.txt", "text/plain", b"Synthetic UTF-8 compliance notes.", "utf8_text"),
        (
            "guide.md",
            "text/markdown",
            b"# Guide\n\n- Governed synthetic retrieval",
            "markdown_text",
        ),
    ],
)
def test_multipart_endpoint_supports_all_allowlisted_formats(
    app: FastAPI,
    client: TestClient,
    filename: str,
    mime_type: str,
    content: bytes,
    expected_parser: str,
) -> None:
    embeddings = DeterministicEmbeddingsService(dimension=3)
    app.dependency_overrides[get_embeddings_service] = lambda: embeddings

    response = client.post(
        "/api/v1/knowledge/files",
        files={"file": (filename, content, mime_type)},
        data={
            "title": "Synthetic title override",
            "source_type": "policy",
            "metadata": json.dumps({"department": "risk"}),
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["filename"] == filename
    assert payload["title"] == "Synthetic title override"
    assert payload["source_type"] == "policy"
    assert payload["parser"] == expected_parser
    assert payload["chunk_count"] >= 1
    assert payload["duplicate"] is False
    assert payload["graph_enrichment_status"] == "not_requested"
    assert len(embeddings.calls) == 1


def test_upload_metadata_and_pdf_pages_flow_to_document_and_chunk_jsonb(
    app: FastAPI,
    client: TestClient,
    db_session: Session,
) -> None:
    app.dependency_overrides[get_embeddings_service] = lambda: DeterministicEmbeddingsService(3)
    content = build_pdf(
        "First synthetic page describes Loan Portal controls and documented ownership.",
        "Second synthetic page requires Risk Team approval and human escalation evidence.",
    )

    response = client.post(
        "/api/v1/knowledge/files",
        files={"file": ("../unsafe/policy.pdf", content, "application/pdf")},
        data={"metadata": '{"department":"risk"}'},
    )

    assert response.status_code == 201
    payload = response.json()
    document = KnowledgeDocumentRepository(db_session).get_by_id(UUID(payload["document_id"]))
    chunks = KnowledgeChunkRepository(db_session).list_by_document(UUID(payload["document_id"]))
    assert payload["filename"] == "policy.pdf"
    assert document is not None
    assert document.metadata["file"]["page_count"] == 2
    assert document.metadata["file"]["raw_binary_retained"] is False
    assert document.metadata["user"] == {"department": "risk"}
    assert document.metadata["content_trust"] == "untrusted_evidence"
    assert chunks[0].metadata["source_page_start"] == 1
    assert chunks[0].metadata["source_page_end"] == 2


def test_equivalent_normalized_files_reuse_document_and_embeddings(
    app: FastAPI,
    client: TestClient,
) -> None:
    embeddings = DeterministicEmbeddingsService(dimension=3)
    app.dependency_overrides[get_embeddings_service] = lambda: embeddings

    first = client.post(
        "/api/v1/knowledge/files",
        files={"file": ("first.txt", b"Same evidence.\r\n\r\nHuman review.", "text/plain")},
    )
    second = client.post(
        "/api/v1/knowledge/files",
        files={"file": ("second.txt", b"Same evidence.\n\nHuman review.  ", "text/plain")},
    )

    assert first.status_code == 201 and second.status_code == 201
    assert second.json()["document_id"] == first.json()["document_id"]
    assert second.json()["duplicate"] is True
    assert len(embeddings.calls) == 1


def test_uploaded_docx_becomes_attributed_rag_evidence(
    app: FastAPI,
    client: TestClient,
    db_session: Session,
) -> None:
    embeddings = DeterministicEmbeddingsService(dimension=3)
    app.dependency_overrides[get_embeddings_service] = lambda: embeddings

    response = client.post(
        "/api/v1/knowledge/files",
        files={"file": ("controls.docx", build_docx(), DOCX_MIME)},
        data={"source_type": "policy"},
    )

    assert response.status_code == 201
    document_id = UUID(response.json()["document_id"])
    document = KnowledgeDocumentRepository(db_session).get_by_id(document_id)
    chunk = KnowledgeChunkRepository(db_session).list_by_document(document_id)[0]
    assert document is not None
    expected = RetrievedEvidence(
        chunk_id=chunk.chunk_id,
        document_id=document.document_id,
        document_title=document.title,
        content=chunk.content,
        similarity_score=1.0,
        source_type=document.source_type,
        metadata={"document": document.metadata, "chunk": chunk.metadata},
    )
    vector_repository = Mock(spec=KnowledgeChunkRepository)
    vector_repository.search_similar.return_value = [expected]
    retrieval = RetrievalService(
        chunks=vector_repository,
        embeddings=embeddings,
        top_k=5,
        similarity_threshold=0.35,
    )

    results = retrieval.search("human approval controls", document_id=document_id)

    assert results == [expected]
    assert results[0].metadata["document"]["file"]["file_format"] == "docx"
    vector_repository.search_similar.assert_called_once()


def test_endpoint_returns_controlled_upload_errors(
    app: FastAPI,
    client: TestClient,
) -> None:
    app.dependency_overrides[get_embeddings_service] = lambda: DeterministicEmbeddingsService(3)
    unsupported = client.post(
        "/api/v1/knowledge/files",
        files={"file": ("payload.exe", b"MZ", "application/octet-stream")},
    )
    empty = client.post(
        "/api/v1/knowledge/files",
        files={"file": ("empty.txt", b"", "text/plain")},
    )

    assert unsupported.status_code == 415
    assert unsupported.json()["error"]["code"] == "unsupported_file_type"
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "empty_file"

    bounded = FileIngestionService(
        parsers=DocumentParserRouter([]),
        knowledge=object(),  # type: ignore[arg-type]
        graph=None,
        max_upload_size_bytes=3,
    )
    app.dependency_overrides[get_file_ingestion_service] = lambda: bounded
    oversized = client.post(
        "/api/v1/knowledge/files",
        files={"file": ("large.txt", b"four", "text/plain")},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "file_too_large"


class RecordingGraph:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.document_ids: list[UUID] = []

    def enrich(self, document_id: UUID) -> None:
        self.document_ids.append(document_id)
        if self.error is not None:
            raise self.error


def test_optional_graph_failure_preserves_successful_vector_ingestion(
    app: FastAPI,
    client: TestClient,
) -> None:
    graph = RecordingGraph(KnowledgeGraphExtractionError())
    app.dependency_overrides[get_embeddings_service] = lambda: DeterministicEmbeddingsService(3)
    app.dependency_overrides[get_graph_enrichment_service] = lambda: graph

    response = client.post(
        "/api/v1/knowledge/files",
        files={"file": ("policy.md", b"# Policy\n\nLoan review evidence.", "text/markdown")},
        data={"enrich_graph": "true"},
    )

    assert response.status_code == 201
    assert response.json()["graph_enrichment_status"] == "failed"
    assert response.json()["graph_error_code"] == "knowledge_graph_extraction_error"
    assert (
        client.get(f"/api/v1/knowledge/documents/{response.json()['document_id']}").status_code
        == 200
    )


class SyntheticEntityExtractor:
    def extract(self, *, chunk_id: UUID, content: str) -> EntityExtractionResult:
        assert "Loan Portal" in content
        return EntityExtractionResult(
            entities=[
                ExtractedEntity(
                    local_key="portal",
                    canonical_name="Loan Portal",
                    entity_type=KnowledgeEntityType.SYSTEM,
                    confidence=0.9,
                    source_chunk_id=chunk_id,
                ),
                ExtractedEntity(
                    local_key="policy",
                    canonical_name="Review Policy",
                    entity_type=KnowledgeEntityType.POLICY,
                    confidence=0.9,
                    source_chunk_id=chunk_id,
                ),
            ]
        )


class SyntheticRelationshipExtractor:
    def extract(
        self,
        *,
        chunk_id: UUID,
        content: str,
        entities: list[ExtractedEntity],
    ) -> RelationshipExtractionResult:
        assert content and len(entities) == 2
        return RelationshipExtractionResult(
            relationships=[
                ExtractedRelationship(
                    source_entity_key="portal",
                    target_entity_key="policy",
                    relationship_type=KnowledgeRelationshipType.GOVERNED_BY,
                    confidence=0.9,
                    source_chunk_id=chunk_id,
                )
            ]
        )


def test_uploaded_document_participates_in_graph_and_preserves_file_provenance(
    db_session: Session,
) -> None:
    documents = KnowledgeDocumentRepository(db_session)
    chunks = KnowledgeChunkRepository(db_session)
    graph_repository = KnowledgeGraphRepository(db_session)
    knowledge = KnowledgeIngestionService(
        documents=documents,
        chunks=chunks,
        embeddings=DeterministicEmbeddingsService(3),
        chunk_size=1_200,
        chunk_overlap=200,
    )
    graph = KnowledgeGraphEnrichmentService(
        documents=documents,
        chunks=chunks,
        graph=graph_repository,
        entity_extractor=SyntheticEntityExtractor(),
        relationship_extractor=SyntheticRelationshipExtractor(),
    )
    service = FileIngestionService(
        parsers=DocumentParserRouter([PDFDocumentParser(min_extracted_characters=1)]),
        knowledge=knowledge,
        graph=graph,
        max_upload_size_bytes=1024 * 1024,
    )
    pdf = build_pdf("Loan Portal is governed by Review Policy in this synthetic source.")
    upload = UploadFile(
        filename="governance.pdf",
        file=BytesIO(pdf),
        headers={"content-type": "application/pdf"},
    )

    result = asyncio.run(
        service.ingest_upload(
            upload,
            title=None,
            source_type=KnowledgeSourceType.POLICY,
            metadata_json=None,
            enrich_graph=True,
        )
    )
    neighborhood = GraphRetrievalService(
        graph=graph_repository,
        max_depth=2,
        max_entities=20,
        min_confidence=0.5,
    ).search("Loan Portal governance")

    assert result.graph_enrichment_status == "completed"
    assert len(neighborhood.relationships) == 1
    assert neighborhood.evidence[0].metadata["document"]["file"]["filename"] == ("governance.pdf")
    assert neighborhood.evidence[0].metadata["chunk"]["source_pages"] == [1]


class FileEvidenceRetrieval:
    def __init__(self, evidence: RetrievedEvidence) -> None:
        self.evidence = evidence

    def search(self, *_: object, **__: object) -> list[RetrievedEvidence]:
        return [self.evidence]


def test_evidence_agent_tool_treats_file_origin_as_standard_knowledge(
    app: FastAPI,
    client: TestClient,
    db_session: Session,
) -> None:
    app.dependency_overrides[get_embeddings_service] = lambda: DeterministicEmbeddingsService(3)
    response = client.post(
        "/api/v1/knowledge/files",
        files={
            "file": (
                "evidence.md",
                b"# Evidence\n\nHuman approval is required.",
                "text/markdown",
            )
        },
    )
    document_id = UUID(response.json()["document_id"])
    document = KnowledgeDocumentRepository(db_session).get_by_id(document_id)
    chunk = KnowledgeChunkRepository(db_session).list_by_document(document_id)[0]
    assert document is not None
    evidence = RetrievedEvidence(
        chunk_id=chunk.chunk_id,
        document_id=document.document_id,
        document_title=document.title,
        content=chunk.content,
        similarity_score=1.0,
        source_type=document.source_type,
        metadata={"document": document.metadata, "chunk": chunk.metadata},
    )
    registry = build_knowledge_tool_registry(
        retrieval=FileEvidenceRetrieval(evidence),  # type: ignore[arg-type]
        documents=KnowledgeDocumentRepository(db_session),
    )

    result, _, _ = AgentToolPermissions().execute(
        agent=MultiAgentName.EVIDENCE,
        registry=registry,
        name="search_knowledge",
        raw_arguments={"query": "human approval", "top_k": 5},
    )

    assert result.success is True
    assert result.evidence[0].metadata["document"]["file"]["file_format"] == "markdown"
