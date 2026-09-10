"""Atomic per-document graph enrichment tests with synthetic extractors."""

from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.knowledge_graph.enrichment import KnowledgeGraphEnrichmentService
from app.models.knowledge import EmbeddedChunk, KnowledgeSourceType
from app.models.knowledge_graph import KnowledgeEntityType, KnowledgeRelationshipType
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.repositories.knowledge_graph import KnowledgeGraphRepository
from app.schemas.knowledge_graph import (
    EntityExtractionResult,
    ExtractedEntity,
    ExtractedRelationship,
    RelationshipExtractionResult,
)


class SyntheticEntityExtractor:
    def extract(self, *, chunk_id: UUID, content: str) -> EntityExtractionResult:
        assert "Loan Portal" in content
        return EntityExtractionResult(
            entities=[
                ExtractedEntity(
                    local_key="portal",
                    canonical_name="Loan Portal",
                    entity_type=KnowledgeEntityType.SYSTEM,
                    confidence=0.95,
                    source_chunk_id=chunk_id,
                ),
                ExtractedEntity(
                    local_key="policy",
                    canonical_name="Review Policy",
                    entity_type=KnowledgeEntityType.POLICY,
                    confidence=0.9,
                    source_chunk_id=chunk_id,
                ),
            ]
        )


class SyntheticRelationshipExtractor:
    def extract(
        self,
        *,
        chunk_id: UUID,
        content: str,
        entities: list[ExtractedEntity],
    ) -> RelationshipExtractionResult:
        assert len(entities) == 2
        assert "Review Policy" in content
        return RelationshipExtractionResult(
            relationships=[
                ExtractedRelationship(
                    source_entity_key="portal",
                    target_entity_key="policy",
                    relationship_type=KnowledgeRelationshipType.GOVERNED_BY,
                    confidence=0.9,
                    source_chunk_id=chunk_id,
                )
            ]
        )


def test_enrichment_persists_entities_mentions_and_relationships(db_session: Session) -> None:
    document_id = uuid4()
    documents = KnowledgeDocumentRepository(db_session)
    chunks = KnowledgeChunkRepository(db_session)
    documents.create(
        document_id=document_id,
        title="Synthetic review policy",
        source_type=KnowledgeSourceType.SYNTHETIC,
        source_uri=None,
        external_id=None,
        content="Loan Portal is governed by Review Policy.",
        metadata={"synthetic": True},
        content_hash="e" * 64,
    )
    chunks.bulk_create(
        document_id=document_id,
        chunks=[
            EmbeddedChunk(
                chunk_index=0,
                content="Loan Portal is governed by Review Policy.",
                embedding=[1.0, 0.0, 0.0],
                metadata={"synthetic": True},
            )
        ],
    )
    documents.commit()
    graph = KnowledgeGraphRepository(db_session)
    service = KnowledgeGraphEnrichmentService(
        documents=documents,
        chunks=chunks,
        graph=graph,
        entity_extractor=SyntheticEntityExtractor(),
        relationship_extractor=SyntheticRelationshipExtractor(),
    )

    result = service.enrich(document_id)

    assert result.entity_count == 2
    assert result.relationship_count == 1
    assert len(graph.list_entities()) == 2
    relationship = graph.list_relationships()[0]
    assert relationship.relationship_type == KnowledgeRelationshipType.GOVERNED_BY
