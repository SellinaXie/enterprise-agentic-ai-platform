"""SQLAlchemy model for embedded knowledge chunks."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import KNOWLEDGE_EMBEDDING_DIMENSION
from app.db.base import Base
from app.db.models.assessment import utc_now

CHUNK_METADATA = JSON().with_variant(JSONB(), "postgresql")
CHUNK_EMBEDDING = VECTOR(KNOWLEDGE_EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite")


class KnowledgeChunkModel(Base):
    """Store deterministic chunks and their pgvector embeddings."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_knowledge_chunks_document_chunk_index",
        ),
        Index("ix_knowledge_chunks_document_id", "document_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(CHUNK_EMBEDDING, nullable=False)
    chunk_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        CHUNK_METADATA,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.current_timestamp(),
        nullable=False,
    )


Index(
    "ix_knowledge_chunks_embedding_hnsw",
    KnowledgeChunkModel.embedding,
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
).ddl_if(dialect="postgresql")
