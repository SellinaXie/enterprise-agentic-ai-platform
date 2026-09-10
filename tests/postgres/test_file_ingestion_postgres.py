"""Live PostgreSQL V6.5 provenance and normalized deduplication verification."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.knowledge_document import KnowledgeDocumentModel
from app.models.knowledge import KnowledgeSourceSegment, KnowledgeSourceType
from app.rag.ingestion import KnowledgeIngestionService
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.schemas.knowledge import KnowledgeDocumentCreate
from tests.knowledge_fixtures import DeterministicEmbeddingsService

pytestmark = pytest.mark.postgres


def test_postgres_file_metadata_chunk_provenance_and_deduplication(
    postgres_session_factory: sessionmaker[Session],
) -> None:
    with postgres_session_factory() as session:
        documents = KnowledgeDocumentRepository(session)
        chunks = KnowledgeChunkRepository(session)
        embeddings = DeterministicEmbeddingsService(1536)
        service = KnowledgeIngestionService(
            documents=documents,
            chunks=chunks,
            embeddings=embeddings,
            chunk_size=1_200,
            chunk_overlap=200,
        )
        request = KnowledgeDocumentCreate(
            title="Synthetic uploaded PDF",
            source_type=KnowledgeSourceType.POLICY,
            content="Synthetic PostgreSQL file evidence requires human approval.",
            metadata={
                "file": {
                    "filename": "policy.pdf",
                    "mime_type": "application/pdf",
                    "parser_name": "pypdf",
                    "raw_binary_retained": False,
                }
            },
        )
        segments = [
            KnowledgeSourceSegment(
                text=request.content,
                metadata={"page_number": 1},
            )
        ]

        first = service.ingest(request, deduplicate=True, source_segments=segments)
        second = service.ingest(
            request.model_copy(update={"title": "Different binary filename"}),
            deduplicate=True,
            source_segments=segments,
        )
        stored_chunks = chunks.list_by_document(first.document.document_id)
        document_count = session.scalar(select(func.count()).select_from(KnowledgeDocumentModel))

        assert second.document.document_id == first.document.document_id
        assert second.duplicate is True
        assert len(embeddings.calls) == 1
        assert document_count == 1
        assert stored_chunks[0].metadata["source_pages"] == [1]
        assert first.document.metadata["file"]["filename"] == "policy.pdf"
