"""Hybrid merge, fallback, and GraphRAG context tests."""

from dataclasses import replace
from uuid import UUID, uuid4

from app.core.exceptions import KnowledgeGraphUnavailableError, KnowledgeStoreUnavailableError
from app.knowledge_graph.context import build_hybrid_rag_context
from app.knowledge_graph.hybrid import HybridRetrievalService
from app.models.knowledge import KnowledgeSourceType, RetrievalSource, RetrievedEvidence
from app.models.knowledge_graph import (
    GraphEntityResult,
    GraphNeighborhood,
    GraphRelationshipResult,
    KnowledgeEntityType,
    KnowledgeRelationshipType,
)
from app.rag.context import NO_EVIDENCE_CONTEXT


def _evidence(*, chunk_id: UUID | None = None, score: float | None = 0.8) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id=chunk_id or uuid4(),
        document_id=uuid4(),
        document_title="Synthetic policy",
        content="Loan Portal uses Risk Engine.",
        similarity_score=score,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )


def _neighborhood(evidence: list[RetrievedEvidence]) -> GraphNeighborhood:
    source = GraphEntityResult(
        entity_id=uuid4(),
        entity_type=KnowledgeEntityType.SYSTEM,
        canonical_name="Loan Portal",
        normalized_name="loan portal",
    )
    target = GraphEntityResult(
        entity_id=uuid4(),
        entity_type=KnowledgeEntityType.SYSTEM,
        canonical_name="Risk Engine",
        normalized_name="risk engine",
    )
    item = evidence[0] if evidence else _evidence(score=None)
    relationship = GraphRelationshipResult(
        relationship_id=uuid4(),
        source_entity_id=source.entity_id,
        source_entity_name=source.canonical_name,
        target_entity_id=target.entity_id,
        target_entity_name=target.canonical_name,
        relationship_type=KnowledgeRelationshipType.USES,
        confidence=0.9,
        source_document_id=item.document_id,
        source_chunk_id=item.chunk_id,
    )
    return GraphNeighborhood(
        query="Loan Portal risk",
        matched_entities=[source],
        related_entities=[target],
        relationships=[relationship],
        source_document_ids=[item.document_id],
        source_chunk_ids=[item.chunk_id],
        depth_used=1,
        evidence=evidence,
    )


class StubVector:
    def __init__(self, result: object) -> None:
        self.result = result

    def search(self, *_: object, **__: object) -> list[RetrievedEvidence]:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result  # type: ignore[return-value]


class StubGraph:
    def __init__(self, result: object) -> None:
        self.result = result

    def search(self, *_: object, **__: object) -> GraphNeighborhood:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result  # type: ignore[return-value]


def test_hybrid_merge_labels_vector_graph_and_overlap_without_fake_score() -> None:
    overlap_id = uuid4()
    vector_only = _evidence()
    vector_overlap = _evidence(chunk_id=overlap_id, score=0.91)
    graph_overlap = _evidence(chunk_id=overlap_id, score=None)
    graph_only = _evidence(score=None)
    neighborhood = _neighborhood([graph_overlap, graph_only])
    service = HybridRetrievalService(
        vector=StubVector([vector_only, vector_overlap]),  # type: ignore[arg-type]
        graph=StubGraph(neighborhood),  # type: ignore[arg-type]
    )

    result = service.search("Loan Portal risk")
    by_chunk = {item.chunk_id: item for item in result.evidence}

    assert by_chunk[vector_only.chunk_id].retrieval_source == RetrievalSource.VECTOR
    assert by_chunk[overlap_id].retrieval_source == RetrievalSource.BOTH
    assert by_chunk[overlap_id].similarity_score == 0.91
    assert by_chunk[graph_only.chunk_id].retrieval_source == RetrievalSource.GRAPH
    assert by_chunk[graph_only.chunk_id].similarity_score is None
    assert result.metadata.hybrid_evidence_count == 3


def test_vector_failure_falls_back_to_graph() -> None:
    graph_item = _evidence(score=None)
    service = HybridRetrievalService(
        vector=StubVector(KnowledgeStoreUnavailableError()),  # type: ignore[arg-type]
        graph=StubGraph(_neighborhood([graph_item])),  # type: ignore[arg-type]
    )

    result = service.search("Loan Portal")

    assert len(result.evidence) == 1
    assert result.evidence[0].retrieval_source == RetrievalSource.GRAPH
    assert result.metadata.vector_error_code == "knowledge_store_unavailable"


def test_graph_failure_falls_back_to_vector() -> None:
    vector_item = _evidence()
    service = HybridRetrievalService(
        vector=StubVector([vector_item]),  # type: ignore[arg-type]
        graph=StubGraph(KnowledgeGraphUnavailableError()),  # type: ignore[arg-type]
    )

    result = service.search("Loan Portal")

    assert result.evidence == (vector_item,)
    assert result.metadata.degraded_graph_mode is True
    assert result.metadata.graph_error_code == "knowledge_graph_unavailable"


def test_enabled_graph_with_no_matches_preserves_vector_evidence() -> None:
    vector_item = _evidence()
    service = HybridRetrievalService(
        vector=StubVector([vector_item]),  # type: ignore[arg-type]
        graph=StubGraph(GraphNeighborhood.empty("Unknown entity")),  # type: ignore[arg-type]
    )

    result = service.search("Unknown entity")

    assert result.evidence == (vector_item,)
    assert result.metadata.graph_retrieval_used is True
    assert result.metadata.matched_entity_count == 0
    assert result.metadata.degraded_graph_mode is False


def test_both_fail_returns_request_only_safe_result() -> None:
    service = HybridRetrievalService(
        vector=StubVector(KnowledgeStoreUnavailableError()),  # type: ignore[arg-type]
        graph=StubGraph(KnowledgeGraphUnavailableError()),  # type: ignore[arg-type]
    )

    result = service.search("Loan Portal")

    assert result.evidence == ()
    assert result.neighborhood.relationships == []
    assert result.metadata.vector_error_code == "knowledge_store_unavailable"
    assert result.metadata.graph_error_code == "knowledge_graph_unavailable"


def test_graphrag_context_separates_relationships_and_source_evidence() -> None:
    graph_item = _evidence(score=None)
    graph_item = replace(graph_item, retrieval_source=RetrievalSource.GRAPH)
    neighborhood = _neighborhood([graph_item])

    context = build_hybrid_rag_context([graph_item], neighborhood)

    assert "VECTOR EVIDENCE" in context
    assert "GRAPH RELATIONSHIPS" in context
    assert "Loan Portal → uses → Risk Engine" in context
    assert "SOURCE EVIDENCE" in context
    assert str(graph_item.chunk_id) in context
    assert build_hybrid_rag_context([], GraphNeighborhood.empty("none")) == NO_EVIDENCE_CONTEXT
