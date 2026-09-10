"""Bounded typed graph retrieval over the PostgreSQL repository abstraction."""

import logging
from contextlib import suppress
from typing import NoReturn

from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from app.core.exceptions import KnowledgeGraphPersistenceError, KnowledgeGraphUnavailableError
from app.knowledge_graph.ports import KnowledgeGraphRepositoryProtocol
from app.models.knowledge_graph import (
    GraphEntityResult,
    GraphNeighborhood,
    GraphRelationshipResult,
    KnowledgeEntityType,
)

logger = logging.getLogger(__name__)


class GraphRetrievalService:
    """Resolve known entities and return a source-grounded bounded neighborhood."""

    def __init__(
        self,
        *,
        graph: KnowledgeGraphRepositoryProtocol,
        max_depth: int,
        max_entities: int,
        min_confidence: float,
    ) -> None:
        self._graph = graph
        self._max_depth = max_depth
        self._max_entities = max_entities
        self._min_confidence = min_confidence

    def search(
        self,
        query: str,
        *,
        max_depth: int | None = None,
        entity_types: list[KnowledgeEntityType] | None = None,
    ) -> GraphNeighborhood:
        """Use deterministic entity-name matching and no user-supplied SQL/graph language."""
        resolved_depth = min(max_depth or self._max_depth, self._max_depth)
        logger.info("graph_retrieval_started", extra={"graph_depth": resolved_depth})
        try:
            matches = self._graph.find_matching_query(
                query,
                limit=self._max_entities,
                entity_types=entity_types,
            )
            if not matches:
                logger.info(
                    "graph_retrieval_completed",
                    extra={"matched_entity_count": 0, "relationship_count": 0},
                )
                return GraphNeighborhood.empty(query)
            traversal = self._graph.get_neighborhood(
                [entity.entity_id for entity in matches],
                max_depth=resolved_depth,
                max_entities=self._max_entities,
                min_confidence=self._min_confidence,
            )
        except (OperationalError, ProgrammingError) as exc:
            with suppress(SQLAlchemyError):
                self._graph.rollback()
            self._raise_database_error(exc)
        except SQLAlchemyError as exc:
            with suppress(SQLAlchemyError):
                self._graph.rollback()
            self._raise_database_error(exc)

        entities = {
            entity.entity_id: entity
            for entity in (*traversal.matched_entities, *traversal.related_entities)
        }
        evidence_by_chunk = {item.chunk_id: item for item in traversal.evidence}
        relationships = []
        for relationship in traversal.relationships:
            source = entities.get(relationship.source_entity_id)
            target = entities.get(relationship.target_entity_id)
            provenance = evidence_by_chunk.get(relationship.source_chunk_id)
            if source is None or target is None or provenance is None:
                continue
            relationships.append(
                GraphRelationshipResult(
                    relationship_id=relationship.relationship_id,
                    source_entity_id=source.entity_id,
                    source_entity_name=source.canonical_name,
                    target_entity_id=target.entity_id,
                    target_entity_name=target.canonical_name,
                    relationship_type=relationship.relationship_type,
                    description=relationship.description,
                    confidence=relationship.confidence,
                    source_document_id=provenance.document_id,
                    source_chunk_id=provenance.chunk_id,
                )
            )
        result = GraphNeighborhood(
            query=query,
            matched_entities=[_entity_result(entity) for entity in traversal.matched_entities],
            related_entities=[_entity_result(entity) for entity in traversal.related_entities],
            relationships=relationships,
            source_document_ids=sorted(
                {item.document_id for item in traversal.evidence},
                key=str,
            ),
            source_chunk_ids=sorted(evidence_by_chunk, key=str),
            depth_used=traversal.depth_used,
            evidence=list(traversal.evidence),
        )
        logger.info(
            "graph_retrieval_completed",
            extra={
                "matched_entity_count": len(result.matched_entities),
                "relationship_count": len(result.relationships),
                "graph_depth": result.depth_used,
            },
        )
        return result

    @staticmethod
    def _raise_database_error(exc: SQLAlchemyError) -> NoReturn:
        logger.error("graph_retrieval_failed", extra={"database_error_type": type(exc).__name__})
        if isinstance(exc, (OperationalError, ProgrammingError)):
            raise KnowledgeGraphUnavailableError from exc
        raise KnowledgeGraphPersistenceError from exc


def _entity_result(entity: object) -> GraphEntityResult:
    return GraphEntityResult.model_validate(entity, from_attributes=True)
