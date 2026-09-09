"""SQLAlchemy model for normalized knowledge documents."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Enum, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.assessment import utc_now
from app.models.knowledge import KnowledgeSourceType

DOCUMENT_METADATA = JSON().with_variant(JSONB(), "postgresql")


class KnowledgeDocumentModel(Base):
    """Store normalized text separately from assessment application state."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("ix_knowledge_documents_source_type", "source_type"),
        Index("ix_knowledge_documents_content_hash", "content_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_type: Mapped[KnowledgeSourceType] = mapped_column(
        Enum(
            KnowledgeSourceType,
            values_callable=lambda values: [value.value for value in values],
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            name="knowledge_source_type_values",
            length=30,
        ),
        nullable=False,
    )
    source_uri: Mapped[str | None] = mapped_column(String(2_000), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        DOCUMENT_METADATA,
        nullable=False,
        default=dict,
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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
