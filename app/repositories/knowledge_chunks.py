"""Persistence and pgvector similarity search for knowledge chunks."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.knowledge_chunk import KnowledgeChunkModel
from app.db.models.knowledge_document import KnowledgeDocumentModel
from app.models.knowledge import (
    EmbeddedChunk,
    KnowledgeChunkRecord,
    KnowledgeSourceType,
    RetrievedEvidence,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_record(model: KnowledgeChunkModel) -> KnowledgeChunkRecord:
    return KnowledgeChunkRecord(
        chunk_id=model.id,
        document_id=model.document_id,
        chunk_index=model.chunk_index,
        content=model.content,
        embedding=[float(value) for value in model.embedding],
        metadata=dict(model.chunk_metadata),
        created_at=_as_utc(model.created_at),
    )


class KnowledgeChunkRepository:
    """Store chunks and execute cosine similarity queries without LLM logic."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def bulk_create(
        self,
        *,
        document_id: UUID,
        chunks: list[EmbeddedChunk],
    ) -> list[KnowledgeChunkRecord]:
        models = [
            KnowledgeChunkModel(
                id=uuid4(),
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                embedding=chunk.embedding,
                chunk_metadata=dict(chunk.metadata),
            )
            for chunk in chunks
        ]
        self._session.add_all(models)
        self._session.flush()
        return [_to_record(model) for model in models]

    def list_by_document(self, document_id: UUID) -> list[KnowledgeChunkRecord]:
        statement = (
            select(KnowledgeChunkModel)
            .where(KnowledgeChunkModel.document_id == document_id)
            .order_by(KnowledgeChunkModel.chunk_index)
        )
        return [_to_record(model) for model in self._session.scalars(statement)]

    def search_similar(
        self,
        query_embedding: list[float],
        *,
        limit: int,
        similarity_threshold: float,
        source_type: KnowledgeSourceType | None = None,
        document_id: UUID | None = None,
    ) -> list[RetrievedEvidence]:
        distance = KnowledgeChunkModel.embedding.cosine_distance(query_embedding)
        similarity = (1 - distance).label("similarity_score")
        statement = (
            select(KnowledgeChunkModel, KnowledgeDocumentModel, similarity)
            .join(
                KnowledgeDocumentModel,
                KnowledgeDocumentModel.id == KnowledgeChunkModel.document_id,
            )
            .where(distance <= 1 - similarity_threshold)
            .order_by(distance, KnowledgeChunkModel.id)
            .limit(limit)
        )
        if source_type is not None:
            statement = statement.where(KnowledgeDocumentModel.source_type == source_type)
        if document_id is not None:
            statement = statement.where(KnowledgeChunkModel.document_id == document_id)

        evidence: list[RetrievedEvidence] = []
        seen_chunk_ids: set[UUID] = set()
        for chunk, document, score in self._session.execute(statement):
            if chunk.id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.id)
            evidence.append(
                RetrievedEvidence(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    content=chunk.content,
                    similarity_score=float(score),
                    source_type=document.source_type,
                    metadata={
                        "document": dict(document.document_metadata),
                        "chunk": dict(chunk.chunk_metadata),
                    },
                )
            )
        return evidence

    def rollback(self) -> None:
        """Reset a failed retrieval transaction before higher-level recovery."""
        self._session.rollback()
