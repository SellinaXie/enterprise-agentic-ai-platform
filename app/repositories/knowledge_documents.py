"""Persistence operations for normalized knowledge documents."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.knowledge_document import KnowledgeDocumentModel
from app.models.knowledge import KnowledgeDocumentRecord, KnowledgeSourceType


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _to_record(model: KnowledgeDocumentModel) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        document_id=model.id,
        title=model.title,
        source_type=model.source_type,
        source_uri=model.source_uri,
        external_id=model.external_id,
        content=model.content,
        metadata=dict(model.document_metadata),
        content_hash=model.content_hash,
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


class KnowledgeDocumentRepository:
    """Store and retrieve documents without retrieval or LLM decisions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        document_id: UUID,
        title: str,
        source_type: KnowledgeSourceType,
        source_uri: str | None,
        external_id: str | None,
        content: str,
        metadata: Mapping[str, Any],
        content_hash: str,
    ) -> KnowledgeDocumentRecord:
        model = KnowledgeDocumentModel(
            id=document_id,
            title=title,
            source_type=source_type,
            source_uri=source_uri,
            external_id=external_id,
            content=content,
            document_metadata=dict(metadata),
            content_hash=content_hash,
        )
        self._session.add(model)
        self._session.flush()
        return _to_record(model)

    def get_by_id(self, document_id: UUID) -> KnowledgeDocumentRecord | None:
        model = self._session.get(KnowledgeDocumentModel, document_id)
        return _to_record(model) if model is not None else None

    def list(self, *, limit: int = 100) -> list[KnowledgeDocumentRecord]:
        statement = (
            select(KnowledgeDocumentModel)
            .order_by(KnowledgeDocumentModel.created_at, KnowledgeDocumentModel.id)
            .limit(limit)
        )
        return [_to_record(model) for model in self._session.scalars(statement)]

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
