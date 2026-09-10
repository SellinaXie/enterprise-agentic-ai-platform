"""PostgreSQL/SQLAlchemy repository abstraction for the V6 knowledge graph."""

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models.assessment import utc_now
from app.db.models.knowledge_chunk import KnowledgeChunkModel
from app.db.models.knowledge_document import KnowledgeDocumentModel
from app.db.models.knowledge_entity import KnowledgeEntityMentionModel, KnowledgeEntityModel
from app.db.models.knowledge_relationship import KnowledgeRelationshipModel
from app.knowledge_graph.normalization import canonicalize_entity_name, normalize_entity_name
from app.models.knowledge import RetrievalSource, RetrievedEvidence
from app.models.knowledge_graph import (
    GraphTraversalData,
    KnowledgeEntityMentionRecord,
    KnowledgeEntityRecord,
    KnowledgeEntityType,
    KnowledgeRelationshipRecord,
    KnowledgeRelationshipType,
)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _entity_record(model: KnowledgeEntityModel) -> KnowledgeEntityRecord:
    return KnowledgeEntityRecord(
        entity_id=model.id,
        entity_type=model.entity_type,
        canonical_name=model.canonical_name,
        normalized_name=model.normalized_name,
        description=model.description,
        metadata=dict(model.entity_metadata),
        created_at=_as_utc(model.created_at),
        updated_at=_as_utc(model.updated_at),
    )


def _mention_record(model: KnowledgeEntityMentionModel) -> KnowledgeEntityMentionRecord:
    return KnowledgeEntityMentionRecord(
        mention_id=model.id,
        entity_id=model.entity_id,
        document_id=model.document_id,
        chunk_id=model.chunk_id,
        mention_text=model.mention_text,
        confidence=float(model.confidence),
        metadata=dict(model.mention_metadata),
        created_at=_as_utc(model.created_at),
    )


def _relationship_record(model: KnowledgeRelationshipModel) -> KnowledgeRelationshipRecord:
    return KnowledgeRelationshipRecord(
        relationship_id=model.id,
        source_entity_id=model.source_entity_id,
        target_entity_id=model.target_entity_id,
        relationship_type=model.relationship_type,
        description=model.description,
        confidence=float(model.confidence),
        source_chunk_id=model.source_chunk_id,
        metadata=dict(model.relationship_metadata),
        created_at=_as_utc(model.created_at),
    )


class KnowledgeGraphRepository:
    """Hide relational upserts and bounded traversal from extraction and agent code."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_entity(
        self,
        *,
        entity_type: KnowledgeEntityType,
        canonical_name: str,
        description: str | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeEntityRecord:
        """Resolve only deterministic same-type whitespace/case duplicates."""
        canonical = canonicalize_entity_name(canonical_name)
        normalized = normalize_entity_name(canonical)
        if not normalized:
            raise ValueError("Entity name must contain non-whitespace characters")
        statement = select(KnowledgeEntityModel).where(
            KnowledgeEntityModel.entity_type == entity_type,
            KnowledgeEntityModel.normalized_name == normalized,
        )
        model = self._session.scalar(statement)
        if model is None:
            model = KnowledgeEntityModel(
                id=uuid4(),
                entity_type=entity_type,
                canonical_name=canonical,
                normalized_name=normalized,
                description=description,
                entity_metadata=dict(metadata or {}),
            )
            self._session.add(model)
            self._session.flush()
        elif model.description is None and description:
            model.description = description
            model.updated_at = utc_now()
            self._session.flush()
        return _entity_record(model)

    def get_entity(self, entity_id: UUID) -> KnowledgeEntityRecord | None:
        model = self._session.get(KnowledgeEntityModel, entity_id)
        return _entity_record(model) if model is not None else None

    def find_entity(
        self,
        *,
        entity_type: KnowledgeEntityType,
        name: str,
    ) -> KnowledgeEntityRecord | None:
        normalized = normalize_entity_name(name)
        statement = select(KnowledgeEntityModel).where(
            KnowledgeEntityModel.entity_type == entity_type,
            KnowledgeEntityModel.normalized_name == normalized,
        )
        model = self._session.scalar(statement)
        return _entity_record(model) if model is not None else None

    def find_matching_query(
        self,
        query: str,
        *,
        limit: int,
        entity_types: Sequence[KnowledgeEntityType] | None = None,
    ) -> list[KnowledgeEntityRecord]:
        """Match known names deterministically without accepting a graph query language."""
        normalized_query = normalize_entity_name(query)
        if not normalized_query:
            return []
        statement = select(KnowledgeEntityModel).order_by(
            KnowledgeEntityModel.normalized_name,
            KnowledgeEntityModel.id,
        )
        if entity_types:
            statement = statement.where(KnowledgeEntityModel.entity_type.in_(entity_types))
        # The bounded candidate scan is portable across PostgreSQL and SQLite tests. Matching is
        # done in Python so extracted '%'/'_' characters cannot become SQL LIKE wildcards.
        candidates = self._session.scalars(statement.limit(max(100, limit * 50))).all()
        matches = [
            model
            for model in candidates
            if re.search(
                rf"(?<!\w){re.escape(model.normalized_name)}(?!\w)",
                normalized_query,
            )
        ]
        matches.sort(key=lambda model: (-len(model.normalized_name), str(model.id)))
        return [_entity_record(model) for model in matches[:limit]]

    def add_mention(
        self,
        *,
        entity_id: UUID,
        document_id: UUID,
        chunk_id: UUID,
        mention_text: str,
        confidence: float,
        metadata: Mapping[str, Any] | None = None,
    ) -> KnowledgeEntityMentionRecord:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Mention confidence must be between zero and one")
        if self._session.get(KnowledgeEntityModel, entity_id) is None:
            raise ValueError("Mention references an unknown entity")
        chunk = self._session.get(KnowledgeChunkModel, chunk_id)
        if chunk is None:
            raise ValueError("Mention references an unknown chunk")
        if chunk.document_id != document_id:
            raise ValueError("Mention document must own the source chunk")
        statement = select(KnowledgeEntityMentionModel).where(
            KnowledgeEntityMentionModel.entity_id == entity_id,
            KnowledgeEntityMentionModel.chunk_id == chunk_id,
        )
        model = self._session.scalar(statement)
        if model is None:
            model = KnowledgeEntityMentionModel(
                id=uuid4(),
                entity_id=entity_id,
                document_id=document_id,
                chunk_id=chunk_id,
                mention_text=canonicalize_entity_name(mention_text),
                confidence=confidence,
                mention_metadata=dict(metadata or {}),
            )
            self._session.add(model)
            self._session.flush()
        return _mention_record(model)

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
    ) -> KnowledgeRelationshipRecord:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("Relationship confidence must be between zero and one")
        if source_entity_id == target_entity_id:
            raise ValueError("Self-relationships are not allowed")
        if self._session.get(KnowledgeEntityModel, source_entity_id) is None:
            raise ValueError("Relationship references an unknown source entity")
        if self._session.get(KnowledgeEntityModel, target_entity_id) is None:
            raise ValueError("Relationship references an unknown target entity")
        if self._session.get(KnowledgeChunkModel, source_chunk_id) is None:
            raise ValueError("Relationship references an unknown source chunk")
        statement = select(KnowledgeRelationshipModel).where(
            KnowledgeRelationshipModel.source_entity_id == source_entity_id,
            KnowledgeRelationshipModel.target_entity_id == target_entity_id,
            KnowledgeRelationshipModel.relationship_type == relationship_type,
            KnowledgeRelationshipModel.source_chunk_id == source_chunk_id,
        )
        model = self._session.scalar(statement)
        if model is None:
            model = KnowledgeRelationshipModel(
                id=uuid4(),
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relationship_type=relationship_type,
                description=description,
                confidence=confidence,
                source_chunk_id=source_chunk_id,
                relationship_metadata=dict(metadata or {}),
            )
            self._session.add(model)
            self._session.flush()
        return _relationship_record(model)

    def get_neighborhood(
        self,
        seed_entity_ids: Sequence[UUID],
        *,
        max_depth: int,
        max_entities: int,
        min_confidence: float,
    ) -> GraphTraversalData:
        """Traverse incoming and outgoing edges breadth-first with hard depth/result bounds."""
        ordered_seeds = list(dict.fromkeys(seed_entity_ids))[:max_entities]
        visited = set(ordered_seeds)
        frontier = set(ordered_seeds)
        relationships: dict[UUID, KnowledgeRelationshipModel] = {}
        depth_used = 0

        for depth in range(1, max_depth + 1):
            if not frontier:
                break
            statement = (
                select(KnowledgeRelationshipModel)
                .where(
                    or_(
                        KnowledgeRelationshipModel.source_entity_id.in_(frontier),
                        KnowledgeRelationshipModel.target_entity_id.in_(frontier),
                    ),
                    KnowledgeRelationshipModel.confidence >= min_confidence,
                )
                .order_by(
                    KnowledgeRelationshipModel.created_at,
                    KnowledgeRelationshipModel.id,
                )
                .limit(max_entities * 8)
            )
            edges = list(self._session.scalars(statement))
            if not edges:
                break
            next_frontier: set[UUID] = set()
            for edge in edges:
                endpoints = (edge.source_entity_id, edge.target_entity_id)
                new_ids = [value for value in endpoints if value not in visited]
                if new_ids and len(visited) + len(new_ids) > max_entities:
                    continue
                relationships.setdefault(edge.id, edge)
                next_frontier.update(new_ids)
                visited.update(new_ids)
            depth_used = depth
            frontier = next_frontier

        entity_models = list(
            self._session.scalars(
                select(KnowledgeEntityModel)
                .where(KnowledgeEntityModel.id.in_(visited))
                .order_by(KnowledgeEntityModel.normalized_name, KnowledgeEntityModel.id)
            )
        )
        entities_by_id = {model.id: model for model in entity_models}
        matched = tuple(
            _entity_record(entities_by_id[entity_id])
            for entity_id in ordered_seeds
            if entity_id in entities_by_id
        )
        related = tuple(
            _entity_record(model) for model in entity_models if model.id not in set(ordered_seeds)
        )

        mention_models = list(
            self._session.scalars(
                select(KnowledgeEntityMentionModel)
                .where(KnowledgeEntityMentionModel.entity_id.in_(visited))
                .order_by(
                    KnowledgeEntityMentionModel.created_at,
                    KnowledgeEntityMentionModel.id,
                )
            )
        )
        chunk_ids = {model.chunk_id for model in mention_models} | {
            model.source_chunk_id for model in relationships.values()
        }
        evidence = self._load_graph_evidence(chunk_ids)
        return GraphTraversalData(
            matched_entities=matched,
            related_entities=related,
            relationships=tuple(
                _relationship_record(model)
                for model in sorted(relationships.values(), key=lambda item: str(item.id))
            ),
            mentions=tuple(_mention_record(model) for model in mention_models),
            evidence=tuple(evidence),
            depth_used=depth_used,
        )

    def _load_graph_evidence(self, chunk_ids: set[UUID]) -> list[RetrievedEvidence]:
        if not chunk_ids:
            return []
        statement = (
            select(KnowledgeChunkModel, KnowledgeDocumentModel)
            .join(
                KnowledgeDocumentModel,
                KnowledgeDocumentModel.id == KnowledgeChunkModel.document_id,
            )
            .where(KnowledgeChunkModel.id.in_(chunk_ids))
            .order_by(KnowledgeChunkModel.id)
        )
        return [
            RetrievedEvidence(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title,
                content=chunk.content,
                similarity_score=None,
                source_type=document.source_type,
                metadata={
                    "document": dict(document.document_metadata),
                    "chunk": dict(chunk.chunk_metadata),
                },
                retrieval_source=RetrievalSource.GRAPH,
            )
            for chunk, document in self._session.execute(statement)
        ]

    def list_entities(self) -> list[KnowledgeEntityRecord]:
        models = self._session.scalars(
            select(KnowledgeEntityModel).order_by(
                KnowledgeEntityModel.normalized_name,
                KnowledgeEntityModel.id,
            )
        )
        return [_entity_record(model) for model in models]

    def list_relationships(self) -> list[KnowledgeRelationshipRecord]:
        models = self._session.scalars(
            select(KnowledgeRelationshipModel).order_by(KnowledgeRelationshipModel.id)
        )
        return [_relationship_record(model) for model in models]

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
