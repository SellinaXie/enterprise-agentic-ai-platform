"""Live PostgreSQL round trip for V6 relational graph records."""

from uuid import uuid4

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.models.knowledge import EmbeddedChunk, KnowledgeSourceType, RetrievalSource
from app.models.knowledge_graph import KnowledgeEntityType, KnowledgeRelationshipType
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.repositories.knowledge_graph import KnowledgeGraphRepository

pytestmark = pytest.mark.postgres


def test_postgres_graph_uuid_jsonb_provenance_and_traversal_round_trip(
    postgres_session_factory: sessionmaker[Session],
    postgres_engine: Engine,
) -> None:
    with postgres_session_factory() as session:
        document_id = uuid4()
        documents = KnowledgeDocumentRepository(session)
        chunks = KnowledgeChunkRepository(session)
        documents.create(
            document_id=document_id,
            title="Synthetic PostgreSQL graph source",
            source_type=KnowledgeSourceType.SYNTHETIC,
            source_uri=None,
            external_id="synthetic-v6-postgres",
            content="Loan Portal is governed by Review Policy.",
            metadata={"fixture": "postgres", "nested": {"version": 6}},
            content_hash="d" * 64,
        )
        chunk = chunks.bulk_create(
            document_id=document_id,
            chunks=[
                EmbeddedChunk(
                    chunk_index=0,
                    content="Loan Portal is governed by Review Policy.",
                    embedding=[1.0] + [0.0] * 1535,
                    metadata={"synthetic": True},
                )
            ],
        )[0]
        graph = KnowledgeGraphRepository(session)
        portal = graph.upsert_entity(
            entity_type=KnowledgeEntityType.SYSTEM,
            canonical_name="Loan Portal",
            description="Synthetic system",
            metadata={"criticality": "medium", "owners": ["operations"]},
        )
        policy = graph.upsert_entity(
            entity_type=KnowledgeEntityType.POLICY,
            canonical_name="Review Policy",
            description="Synthetic policy",
            metadata={"control": True},
        )
        for entity in (portal, policy):
            graph.add_mention(
                entity_id=entity.entity_id,
                document_id=document_id,
                chunk_id=chunk.chunk_id,
                mention_text=entity.canonical_name,
                confidence=0.9,
                metadata={"extractor": "synthetic"},
            )
        relationship = graph.add_relationship(
            source_entity_id=portal.entity_id,
            target_entity_id=policy.entity_id,
            relationship_type=KnowledgeRelationshipType.GOVERNED_BY,
            description="Explicitly supported by the synthetic source",
            confidence=0.95,
            source_chunk_id=chunk.chunk_id,
            metadata={"extractor": "synthetic", "schema_version": 1},
        )
        graph.commit()

        reloaded = graph.get_entity(portal.entity_id)
        traversal = graph.get_neighborhood(
            [portal.entity_id], max_depth=2, max_entities=20, min_confidence=0.5
        )

        assert reloaded is not None
        assert reloaded.entity_id == portal.entity_id
        assert reloaded.metadata == {"criticality": "medium", "owners": ["operations"]}
        assert reloaded.created_at.tzinfo is not None
        assert traversal.relationships[0].relationship_id == relationship.relationship_id
        assert traversal.relationships[0].metadata == {
            "extractor": "synthetic",
            "schema_version": 1,
        }
        assert traversal.evidence[0].document_id == document_id
        assert traversal.evidence[0].chunk_id == chunk.chunk_id
        assert traversal.evidence[0].retrieval_source == RetrievalSource.GRAPH
        assert traversal.evidence[0].similarity_score is None

    schema = inspect(postgres_engine)
    entity_constraints = {
        item["name"] for item in schema.get_unique_constraints("knowledge_entities")
    }
    relationship_constraints = {
        item["name"] for item in schema.get_unique_constraints("knowledge_relationships")
    }
    relationship_foreign_keys = {
        tuple(item["constrained_columns"])
        for item in schema.get_foreign_keys("knowledge_relationships")
    }
    assert "uq_knowledge_entities_type_normalized_name" in entity_constraints
    assert "uq_knowledge_relationships_source_target_type_chunk" in relationship_constraints
    assert {("source_entity_id",), ("target_entity_id",), ("source_chunk_id",)} <= (
        relationship_foreign_keys
    )
