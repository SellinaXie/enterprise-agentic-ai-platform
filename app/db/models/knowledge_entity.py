"""SQLAlchemy models for V6 knowledge entities and source mentions."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.assessment import utc_now
from app.models.knowledge_graph import KnowledgeEntityType

GRAPH_METADATA = JSON().with_variant(JSONB(), "postgresql")


class KnowledgeEntityModel(Base):
    """Store normalized graph identity independently of source occurrences."""

    __tablename__ = "knowledge_entities"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "normalized_name",
            name="uq_knowledge_entities_type_normalized_name",
        ),
        Index("ix_knowledge_entities_normalized_name", "normalized_name"),
        Index("ix_knowledge_entities_entity_type", "entity_type"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    entity_type: Mapped[KnowledgeEntityType] = mapped_column(
        Enum(
            KnowledgeEntityType,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="knowledge_entity_type_values",
            length=30,
        ),
        nullable=False,
    )
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        GRAPH_METADATA,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.current_timestamp(),
        nullable=False,
    )


class KnowledgeEntityMentionModel(Base):
    """Link a resolved entity to the exact document chunk that mentions it."""

    __tablename__ = "knowledge_entity_mentions"
    __table_args__ = (
        UniqueConstraint(
            "entity_id",
            "chunk_id",
            name="uq_knowledge_entity_mentions_entity_chunk",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="knowledge_entity_mentions_confidence_range",
        ),
        Index("ix_knowledge_entity_mentions_entity_id", "entity_id"),
        Index("ix_knowledge_entity_mentions_document_id", "document_id"),
        Index("ix_knowledge_entity_mentions_chunk_id", "chunk_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    entity_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    mention_text: Mapped[str] = mapped_column(String(500), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    mention_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        GRAPH_METADATA,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.current_timestamp(),
        nullable=False,
    )
