"""Fast repository tests for relational graph identity and traversal."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.knowledge_graph.retrieval import GraphRetrievalService
from app.models.knowledge import EmbeddedChunk, KnowledgeSourceType, RetrievalSource
from app.models.knowledge_graph import KnowledgeEntityType, KnowledgeRelationshipType
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.repositories.knowledge_graph import KnowledgeGraphRepository


def _source(db_session: Session) -> tuple[UUID, UUID]:
    document_id = uuid4()
    KnowledgeDocumentRepository(db_session).create(
        document_id=document_id,
        title="Synthetic underwriting policy",
        source_type=KnowledgeSourceType.SYNTHETIC,
        source_uri=None,
        external_id=None,
        content="Loan Portal uses Risk Engine governed by Review Policy.",
        metadata={"synthetic": True},
        content_hash="f" * 64,
    )
    chunks = KnowledgeChunkRepository(db_session).bulk_create(
        document_id=document_id,
        chunks=[
            EmbeddedChunk(
                chunk_index=0,
                content="Loan Portal uses Risk Engine governed by Review Policy.",
                embedding=[1.0, 0.0, 0.0],
                metadata={"synthetic": True},
            )
        ],
    )
    db_session.commit()
    return document_id, chunks[0].chunk_id


def test_entity_resolution_is_case_and_whitespace_deterministic(db_session: Session) -> None:
    graph = KnowledgeGraphRepository(db_session)
    first = graph.upsert_entity(
        entity_type=KnowledgeEntityType.SYSTEM,
        canonical_name=" Loan   Portal ",
        description=None,
    )
    duplicate = graph.upsert_entity(
        entity_type=KnowledgeEntityType.SYSTEM,
        canonical_name="loan portal",
        description="Synthetic system",
    )
    different_type = graph.upsert_entity(
        entity_type=KnowledgeEntityType.PROCESS,
        canonical_name="Loan Portal",
        description=None,
    )

    assert duplicate.entity_id == first.entity_id
    assert duplicate.description == "Synthetic system"
    assert different_type.entity_id != first.entity_id
    assert len(graph.list_entities()) == 2


def test_mentions_validate_provenance_and_deduplicate(db_session: Session) -> None:
    document_id, chunk_id = _source(db_session)
    graph = KnowledgeGraphRepository(db_session)
    entity = graph.upsert_entity(
        entity_type=KnowledgeEntityType.SYSTEM,
        canonical_name="Loan Portal",
        description=None,
    )
    first = graph.add_mention(
        entity_id=entity.entity_id,
        document_id=document_id,
        chunk_id=chunk_id,
        mention_text="Loan Portal",
        confidence=0.9,
    )
    duplicate = graph.add_mention(
        entity_id=entity.entity_id,
        document_id=document_id,
        chunk_id=chunk_id,
        mention_text="loan portal",
        confidence=0.8,
    )

    assert duplicate.mention_id == first.mention_id
    with pytest.raises(ValueError, match="own"):
        graph.add_mention(
            entity_id=entity.entity_id,
            document_id=uuid4(),
            chunk_id=chunk_id,
            mention_text="Loan Portal",
            confidence=0.9,
        )


def test_relationship_traversal_is_bounded_and_source_grounded(db_session: Session) -> None:
    document_id, chunk_id = _source(db_session)
    graph = KnowledgeGraphRepository(db_session)
    portal = graph.upsert_entity(
        entity_type=KnowledgeEntityType.SYSTEM,
        canonical_name="Loan Portal",
        description=None,
    )
    engine = graph.upsert_entity(
        entity_type=KnowledgeEntityType.SYSTEM,
        canonical_name="Risk Engine",
        description=None,
    )
    policy = graph.upsert_entity(
        entity_type=KnowledgeEntityType.POLICY,
        canonical_name="Review Policy",
        description=None,
    )
    for entity in (portal, engine, policy):
        graph.add_mention(
            entity_id=entity.entity_id,
            document_id=document_id,
            chunk_id=chunk_id,
            mention_text=entity.canonical_name,
            confidence=0.9,
        )
    first = graph.add_relationship(
        source_entity_id=portal.entity_id,
        target_entity_id=engine.entity_id,
        relationship_type=KnowledgeRelationshipType.USES,
        description=None,
        confidence=0.9,
        source_chunk_id=chunk_id,
    )
    duplicate = graph.add_relationship(
        source_entity_id=portal.entity_id,
        target_entity_id=engine.entity_id,
        relationship_type=KnowledgeRelationshipType.USES,
        description=None,
        confidence=0.9,
        source_chunk_id=chunk_id,
    )
    graph.add_relationship(
        source_entity_id=engine.entity_id,
        target_entity_id=policy.entity_id,
        relationship_type=KnowledgeRelationshipType.GOVERNED_BY,
        description=None,
        confidence=0.9,
        source_chunk_id=chunk_id,
    )
    graph.commit()

    depth_one = graph.get_neighborhood(
        [portal.entity_id], max_depth=1, max_entities=20, min_confidence=0.5
    )
    depth_two = graph.get_neighborhood(
        [portal.entity_id], max_depth=2, max_entities=20, min_confidence=0.5
    )

    assert duplicate.relationship_id == first.relationship_id
    assert len(depth_one.relationships) == 1
    assert len(depth_two.relationships) == 2
    assert {item.entity_id for item in depth_two.related_entities} == {
        engine.entity_id,
        policy.entity_id,
    }
    assert depth_two.evidence[0].retrieval_source == RetrievalSource.GRAPH
    assert depth_two.evidence[0].similarity_score is None
    retrieved = GraphRetrievalService(
        graph=graph,
        max_depth=2,
        max_entities=20,
        min_confidence=0.5,
    ).search("How does the Loan Portal manage risk?")
    assert retrieved.matched_entities[0].entity_id == portal.entity_id
    assert len(retrieved.relationships) == 2
    assert retrieved.relationships[0].source_chunk_id == chunk_id
    with pytest.raises(ValueError, match="Self"):
        graph.add_relationship(
            source_entity_id=portal.entity_id,
            target_entity_id=portal.entity_id,
            relationship_type=KnowledgeRelationshipType.RELATED_TO,
            description=None,
            confidence=0.9,
            source_chunk_id=chunk_id,
        )
