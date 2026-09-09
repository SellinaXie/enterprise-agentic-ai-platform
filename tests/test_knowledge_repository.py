"""Knowledge document and chunk persistence tests on fast SQLite fixtures."""

from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.knowledge import EmbeddedChunk
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.schemas.knowledge import KnowledgeDocumentCreate


def test_document_and_chunk_metadata_round_trip(
    db_session: Session,
    synthetic_knowledge_corpus: list[KnowledgeDocumentCreate],
) -> None:
    request = synthetic_knowledge_corpus[0]
    document_id = uuid4()
    documents = KnowledgeDocumentRepository(db_session)
    chunks = KnowledgeChunkRepository(db_session)

    created = documents.create(
        document_id=document_id,
        title=request.title,
        source_type=request.source_type,
        source_uri=request.source_uri,
        external_id=request.external_id,
        content=request.content,
        metadata=request.metadata,
        content_hash="a" * 64,
    )
    chunks.bulk_create(
        document_id=document_id,
        chunks=[
            EmbeddedChunk(
                chunk_index=0,
                content="Synthetic governance chunk.",
                embedding=[1.0, 0.0, 0.0],
                metadata={"ordinal": 0},
            ),
            EmbeddedChunk(
                chunk_index=1,
                content="Synthetic review chunk.",
                embedding=[0.8, 0.2, 0.0],
                metadata={"ordinal": 1},
            ),
        ],
    )
    documents.commit()

    retrieved = documents.get_by_id(document_id)
    stored_chunks = chunks.list_by_document(document_id)

    assert retrieved == created
    assert retrieved is not None and retrieved.metadata == request.metadata
    assert [chunk.chunk_index for chunk in stored_chunks] == [0, 1]
    assert stored_chunks[0].embedding == [1.0, 0.0, 0.0]
    assert stored_chunks[1].metadata == {"ordinal": 1}
