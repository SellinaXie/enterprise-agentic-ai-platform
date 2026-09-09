"""Knowledge ingestion pipeline tests with deterministic embeddings."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import EmbeddingProviderError
from app.db.models.knowledge_document import KnowledgeDocumentModel
from app.rag.ingestion import KnowledgeIngestionService
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.schemas.knowledge import KnowledgeDocumentCreate
from tests.knowledge_fixtures import DeterministicEmbeddingsService


def _service(
    session: Session,
    embeddings: DeterministicEmbeddingsService,
) -> KnowledgeIngestionService:
    return KnowledgeIngestionService(
        documents=KnowledgeDocumentRepository(session),
        chunks=KnowledgeChunkRepository(session),
        embeddings=embeddings,
        chunk_size=120,
        chunk_overlap=20,
    )


def test_ingestion_normalizes_chunks_embeds_and_persists(
    db_session: Session,
    synthetic_knowledge_corpus: list[KnowledgeDocumentCreate],
) -> None:
    embeddings = DeterministicEmbeddingsService(dimension=3)
    service = _service(db_session, embeddings)
    request = synthetic_knowledge_corpus[1].model_copy(
        update={"content": "Compliance evidence.  \r\n\r\nAuthorized review is required. " * 5}
    )

    result = service.ingest(request)
    chunks = KnowledgeChunkRepository(db_session).list_by_document(result.document.document_id)

    assert result.document.content.startswith("Compliance evidence.\n\nAuthorized")
    assert result.chunk_count == len(chunks)
    assert result.chunk_count > 1
    assert len(embeddings.calls) == 1
    assert len(embeddings.calls[0]) == result.chunk_count
    assert all(chunk.metadata["content_hash"] for chunk in chunks)


def test_embedding_failure_rolls_back_document(
    db_session: Session,
    synthetic_knowledge_corpus: list[KnowledgeDocumentCreate],
) -> None:
    embeddings = DeterministicEmbeddingsService(dimension=3)
    embeddings.embed_texts = lambda _: (_ for _ in ()).throw(EmbeddingProviderError())
    service = _service(db_session, embeddings)

    with pytest.raises(EmbeddingProviderError):
        service.ingest(synthetic_knowledge_corpus[0])

    count = db_session.scalar(select(func.count()).select_from(KnowledgeDocumentModel))
    assert count == 0
