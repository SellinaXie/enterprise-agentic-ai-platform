"""Deterministic V6 vector-plus-graph retrieval and fallback behavior."""

import logging
from dataclasses import replace

from app.core.exceptions import ApplicationError
from app.knowledge_graph.context import build_hybrid_rag_context
from app.knowledge_graph.retrieval import GraphRetrievalService
from app.models.knowledge import RetrievalSource, RetrievedEvidence
from app.models.knowledge_graph import (
    GraphNeighborhood,
    GraphRetrievalExecutionMetadata,
    HybridRAGPreparation,
    HybridRetrievalResult,
)
from app.rag.retrieval import RetrievalService, build_retrieval_query
from app.schemas.assessment import AssessmentRequest

logger = logging.getLogger(__name__)


class HybridRetrievalService:
    """Run independent retrieval paths and merge by chunk ID without a synthetic score."""

    def __init__(
        self,
        *,
        vector: RetrievalService,
        graph: GraphRetrievalService,
    ) -> None:
        self._vector = vector
        self._graph = graph

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        max_depth: int | None = None,
    ) -> HybridRetrievalResult:
        vector_error = None
        graph_error = None
        try:
            vector_evidence = self._vector.search(query, top_k=top_k)
        except ApplicationError as exc:
            vector_evidence = []
            vector_error = exc.error_code
            logger.warning("hybrid_vector_fallback", extra={"error_code": vector_error})
        try:
            neighborhood = self._graph.search(query, max_depth=max_depth)
        except ApplicationError as exc:
            neighborhood = GraphNeighborhood.empty(query)
            graph_error = exc.error_code
            logger.warning("graph_retrieval_fallback", extra={"error_code": graph_error})

        merged: dict[object, RetrievedEvidence] = {}
        for item in vector_evidence:
            merged[item.chunk_id] = replace(item, retrieval_source=RetrievalSource.VECTOR)
        for item in neighborhood.evidence:
            existing = merged.get(item.chunk_id)
            if existing is None:
                merged[item.chunk_id] = replace(item, retrieval_source=RetrievalSource.GRAPH)
            else:
                merged[item.chunk_id] = replace(existing, retrieval_source=RetrievalSource.BOTH)

        evidence = tuple(merged.values())
        metadata = GraphRetrievalExecutionMetadata(
            graph_retrieval_used=graph_error is None,
            matched_entity_count=len(neighborhood.matched_entities),
            relationship_count=len(neighborhood.relationships),
            graph_depth_used=neighborhood.depth_used,
            vector_evidence_count=len(vector_evidence),
            graph_evidence_count=len(neighborhood.evidence),
            hybrid_evidence_count=len(evidence),
            degraded_graph_mode=graph_error is not None,
            graph_error_code=graph_error,
            vector_error_code=vector_error,
        )
        logger.info(
            "hybrid_retrieval_completed",
            extra={
                "vector_evidence_count": len(vector_evidence),
                "graph_evidence_count": len(neighborhood.evidence),
                "hybrid_evidence_count": len(evidence),
            },
        )
        return HybridRetrievalResult(
            evidence=evidence,
            neighborhood=neighborhood,
            metadata=metadata,
        )


class HybridRAGService:
    """Build assessment context from hybrid retrieval while preserving V3 fields."""

    def __init__(self, retrieval: HybridRetrievalService) -> None:
        self._retrieval = retrieval

    def prepare(self, request: AssessmentRequest) -> HybridRAGPreparation:
        query = build_retrieval_query(request)
        result = self._retrieval.search(query)
        return HybridRAGPreparation(
            query=query,
            evidence=result.evidence,
            context=build_hybrid_rag_context(result.evidence, result.neighborhood),
            graph_retrieval=result.metadata,
        )
