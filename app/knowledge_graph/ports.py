"""Persistence port keeping GraphRAG business logic independent of SQLAlchemy."""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from uuid import UUID

from app.models.knowledge_graph import (
    GraphTraversalData,
    KnowledgeEntityMentionRecord,
    KnowledgeEntityRecord,
    KnowledgeEntityType,
    KnowledgeRelationshipRecord,
    KnowledgeRelationshipType,
)


class KnowledgeGraphRepositoryProtocol(Protocol):
    """Operations needed by extraction and traversal, regardless of graph backend."""

    def upsert_entity(
        self,
        *,
        entity_type: KnowledgeEntityType,
        canonical_name: str,
        description: str | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeEntityRecord: ...

    def find_matching_query(
        self,
        query: str,
        *,
        limit: int,
        entity_types: Sequence[KnowledgeEntityType] | None = None,
    ) -> list[KnowledgeEntityRecord]: ...

    def add_mention(
        self,
        *,
        entity_id: UUID,
        document_id: UUID,
        chunk_id: UUID,
        mention_text: str,
        confidence: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeEntityMentionRecord: ...

    def add_relationship(
        self,
        *,
        source_entity_id: UUID,
        target_entity_id: UUID,
        relationship_type: KnowledgeRelationshipType,
        description: str | None,
        confidence: float,
        source_chunk_id: UUID,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeRelationshipRecord: ...

    def get_neighborhood(
        self,
        seed_entity_ids: Sequence[UUID],
        *,
        max_depth: int,
        max_entities: int,
        min_confidence: float,
    ) -> GraphTraversalData: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
