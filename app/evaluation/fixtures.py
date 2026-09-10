"""Transparent, dataset-backed retrieval services for network-free V7A runs."""

from uuid import UUID

from app.evaluation.models import BenchmarkDocument, EvaluationDataset
from app.models.knowledge import KnowledgeSourceType, RetrievalSource, RetrievedEvidence
from app.models.knowledge_graph import (
    GraphEntityResult,
    GraphNeighborhood,
    GraphRelationshipResult,
)


class DeterministicVectorRetrieval:
    """Return reviewable fixture rankings without pretending they are live embeddings."""

    def __init__(self, dataset: EvaluationDataset) -> None:
        self._cases = {item.query: item for item in dataset.cases}
        self._documents = {item.chunk_id: item for item in dataset.documents}

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        **_: object,
    ) -> list[RetrievedEvidence]:
        case = self._cases.get(query)
        if case is None:
            return []
        limit = top_k or len(case.fixture.vector_chunk_ids)
        return [
            _evidence(self._documents[chunk_id], rank=rank, origin=RetrievalSource.VECTOR)
            for rank, chunk_id in enumerate(case.fixture.vector_chunk_ids[:limit], start=1)
        ]


class DeterministicGraphRetrieval:
    """Return source-grounded fixture neighborhoods through the V6 result contract."""

    def __init__(self, dataset: EvaluationDataset) -> None:
        self._cases = {item.query: item for item in dataset.cases}
        self._documents = {item.chunk_id: item for item in dataset.documents}
        self._entities = {item.entity_id: item for item in dataset.entities}
        self._relationships = {item.relationship_id: item for item in dataset.relationships}

    def search(
        self,
        query: str,
        *,
        max_depth: int | None = None,
        **_: object,
    ) -> GraphNeighborhood:
        case = self._cases.get(query)
        if case is None:
            return GraphNeighborhood.empty(query)
        fixture = case.fixture.graph
        if max_depth is not None and max_depth < fixture.depth_used:
            return GraphNeighborhood.empty(query)
        depth = fixture.depth_used
        evidence = [
            _evidence(self._documents[chunk_id], rank=rank, origin=RetrievalSource.GRAPH)
            for rank, chunk_id in enumerate(fixture.evidence_chunk_ids, start=1)
        ]
        relationships = []
        for relationship_id in fixture.relationship_ids:
            item = self._relationships[relationship_id]
            source = next(
                entity
                for entity in self._entities.values()
                if entity.canonical_name == item.source_entity
            )
            target = next(
                entity
                for entity in self._entities.values()
                if entity.canonical_name == item.target_entity
            )
            relationships.append(
                GraphRelationshipResult(
                    relationship_id=item.relationship_id,
                    source_entity_id=source.entity_id,
                    source_entity_name=source.canonical_name,
                    target_entity_id=target.entity_id,
                    target_entity_name=target.canonical_name,
                    relationship_type=item.relationship_type,
                    confidence=1.0,
                    source_document_id=item.source_document_id,
                    source_chunk_id=item.source_chunk_id,
                )
            )
        return GraphNeighborhood(
            query=query,
            matched_entities=[self._entity(item) for item in fixture.matched_entity_ids],
            related_entities=[self._entity(item) for item in fixture.related_entity_ids],
            relationships=relationships,
            source_document_ids=list(dict.fromkeys(item.document_id for item in evidence)),
            source_chunk_ids=list(dict.fromkeys(item.chunk_id for item in evidence)),
            depth_used=depth,
            evidence=evidence,
        )

    def _entity(self, entity_id: UUID) -> GraphEntityResult:
        item = self._entities[entity_id]
        return GraphEntityResult(
            entity_id=item.entity_id,
            entity_type=item.entity_type,
            canonical_name=item.canonical_name,
            normalized_name=item.canonical_name.casefold(),
        )


def _evidence(
    document: BenchmarkDocument,
    *,
    rank: int,
    origin: RetrievalSource,
) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id=document.chunk_id,
        document_id=document.document_id,
        document_title=document.title,
        content=document.content,
        similarity_score=max(0.0, 1.0 - (rank - 1) * 0.05)
        if origin == RetrievalSource.VECTOR
        else None,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True, "benchmark_rank": rank},
        retrieval_source=origin,
    )
