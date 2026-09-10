"""SQLAlchemy model for source-grounded V6 knowledge relationships."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.assessment import utc_now
from app.db.models.knowledge_entity import GRAPH_METADATA
from app.models.knowledge_graph import KnowledgeRelationshipType


class KnowledgeRelationshipModel(Base):
    """Store one constrained directed edge with mandatory chunk provenance."""

    __tablename__ = "knowledge_relationships"
    __table_args__ = (
        UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            "source_chunk_id",
            name="uq_knowledge_relationships_source_target_type_chunk",
        ),
        CheckConstraint(
            "source_entity_id <> target_entity_id",
            name="knowledge_relationships_no_self_edge",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="knowledge_relationships_confidence_range",
        ),
        Index("ix_knowledge_relationships_source_entity_id", "source_entity_id"),
        Index("ix_knowledge_relationships_target_entity_id", "target_entity_id"),
        Index("ix_knowledge_relationships_relationship_type", "relationship_type"),
        Index("ix_knowledge_relationships_source_chunk_id", "source_chunk_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    source_entity_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_entity_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[KnowledgeRelationshipType] = mapped_column(
        Enum(
            KnowledgeRelationshipType,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="knowledge_relationship_type_values",
            length=30,
        ),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_chunk_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_metadata: Mapped[dict[str, Any]] = mapped_column(
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
