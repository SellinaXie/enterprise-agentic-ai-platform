"""Deterministic graph enrichment workflow over existing V3 chunks."""

import logging
from typing import NoReturn
from uuid import UUID

from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from app.core.exceptions import (
    ApplicationError,
    KnowledgeDocumentNotFoundError,
    KnowledgeGraphExtractionError,
    KnowledgeGraphPersistenceError,
    KnowledgeGraphUnavailableError,
)
from app.knowledge_graph.extraction import EntityExtractor, RelationshipExtractor
from app.knowledge_graph.ports import KnowledgeGraphRepositoryProtocol
from app.models.knowledge_graph import KnowledgeGraphEnrichmentResult
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository

logger = logging.getLogger(__name__)


class KnowledgeGraphEnrichmentService:
    """Extract and persist a document graph atomically without agent orchestration."""

    def __init__(
        self,
        *,
        documents: KnowledgeDocumentRepository,
        chunks: KnowledgeChunkRepository,
        graph: KnowledgeGraphRepositoryProtocol,
        entity_extractor: EntityExtractor,
        relationship_extractor: RelationshipExtractor,
    ) -> None:
        self._documents = documents
        self._chunks = chunks
        self._graph = graph
        self._entity_extractor = entity_extractor
        self._relationship_extractor = relationship_extractor

    def enrich(self, document_id: UUID) -> KnowledgeGraphEnrichmentResult:
        """Build source-grounded entities, mentions, and edges for one existing document."""
        logger.info("graph_extraction_started", extra={"document_id": str(document_id)})
        try:
            document = self._documents.get_by_id(document_id)
            if document is None:
                raise KnowledgeDocumentNotFoundError
            chunks = self._chunks.list_by_document(document_id)
            entity_ids: set[UUID] = set()
            relationship_ids: set[UUID] = set()

            for chunk in chunks:
                extracted = self._entity_extractor.extract(
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                )
                resolved_by_key = {}
                accepted_entities = []
                for entity in extracted.entities:
                    record = self._graph.upsert_entity(
                        entity_type=entity.entity_type,
                        canonical_name=entity.canonical_name,
                        description=entity.description,
                    )
                    self._graph.add_mention(
                        entity_id=record.entity_id,
                        document_id=document_id,
                        chunk_id=chunk.chunk_id,
                        mention_text=entity.canonical_name,
                        confidence=entity.confidence,
                        metadata={"source_metadata": dict(chunk.metadata)},
                    )
                    entity_ids.add(record.entity_id)
                    resolved_by_key[entity.local_key] = record
                    accepted_entities.append(entity)

                relationships = self._relationship_extractor.extract(
                    chunk_id=chunk.chunk_id,
                    content=chunk.content,
                    entities=accepted_entities,
                )
                for relationship in relationships.relationships:
                    source = resolved_by_key.get(relationship.source_entity_key)
                    target = resolved_by_key.get(relationship.target_entity_key)
                    if source is None or target is None:
                        raise KnowledgeGraphExtractionError
                    record = self._graph.add_relationship(
                        source_entity_id=source.entity_id,
                        target_entity_id=target.entity_id,
                        relationship_type=relationship.relationship_type,
                        description=relationship.description,
                        confidence=relationship.confidence,
                        source_chunk_id=chunk.chunk_id,
                    )
                    relationship_ids.add(record.relationship_id)

            self._graph.commit()
        except ApplicationError:
            self._graph.rollback()
            logger.warning("graph_extraction_failed", extra={"document_id": str(document_id)})
            raise
        except ValueError as exc:
            self._graph.rollback()
            logger.warning("graph_extraction_failed", extra={"document_id": str(document_id)})
            raise KnowledgeGraphExtractionError from exc
        except SQLAlchemyError as exc:
            self._graph.rollback()
            self._raise_database_error(exc)

        logger.info(
            "graph_extraction_completed",
            extra={
                "document_id": str(document_id),
                "entity_count": len(entity_ids),
                "relationship_count": len(relationship_ids),
            },
        )
        return KnowledgeGraphEnrichmentResult(
            document_id=document_id,
            entity_count=len(entity_ids),
            relationship_count=len(relationship_ids),
        )

    @staticmethod
    def _raise_database_error(exc: SQLAlchemyError) -> NoReturn:
        logger.error("graph_database_failure", extra={"database_error_type": type(exc).__name__})
        if isinstance(exc, (OperationalError, ProgrammingError)):
            raise KnowledgeGraphUnavailableError from exc
        raise KnowledgeGraphPersistenceError from exc
