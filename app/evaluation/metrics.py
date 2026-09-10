"""Standard deterministic retrieval, graph, provenance, and aggregate metrics."""

from collections.abc import Iterable, Sequence

from app.evaluation.models import (
    AggregateMetrics,
    BenchmarkDocument,
    BenchmarkRelationship,
    CaseEvaluationResult,
    EvaluationExpectedEvidence,
    GraphMetrics,
    RetrievalMetrics,
)
from app.models.knowledge import RetrievalSource, RetrievedEvidence
from app.models.knowledge_graph import GraphNeighborhood


def calculate_retrieval_metrics(
    evidence: Sequence[RetrievedEvidence],
    expected: EvaluationExpectedEvidence,
    *,
    k: int,
    negative: bool,
) -> RetrievalMetrics:
    """Calculate rank metrics after stable chunk-ID deduplication."""
    if k < 1:
        raise ValueError("k must be positive")
    ranked = _deduplicate_evidence(evidence[:k])
    if negative:
        return RetrievalMetrics(false_positive_rate=1.0 if ranked else 0.0)

    expected_ids = set(expected.chunk_ids)
    use_chunks = bool(expected_ids)
    if not use_chunks:
        expected_ids = set(expected.document_ids)
    if not expected_ids:
        return RetrievalMetrics()

    retrieved_ids = [item.chunk_id if use_chunks else item.document_id for item in ranked]
    relevant = sum(item in expected_ids for item in retrieved_ids)
    first_rank = next(
        (rank for rank, item in enumerate(retrieved_ids, start=1) if item in expected_ids),
        None,
    )
    return RetrievalMetrics(
        hit_rate_at_k=1.0 if relevant else 0.0,
        precision_at_k=relevant / k,
        recall_at_k=relevant / len(expected_ids),
        mrr=0.0 if first_rank is None else 1.0 / first_rank,
    )


def calculate_graph_metrics(
    neighborhood: GraphNeighborhood | None,
    evidence: Sequence[RetrievedEvidence],
    expected: EvaluationExpectedEvidence,
    corpus: Sequence[BenchmarkDocument],
    benchmark_relationships: Sequence[BenchmarkRelationship],
) -> GraphMetrics:
    """Measure expected graph coverage and traceability to the benchmark corpus."""
    found_entities = set()
    found_relationships = set()
    relationships = []
    if neighborhood is not None:
        found_entities = {
            item.canonical_name.casefold()
            for item in (*neighborhood.matched_entities, *neighborhood.related_entities)
        }
        relationships = list(neighborhood.relationships)
        found_relationships = {
            (
                item.source_entity_name.casefold(),
                item.relationship_type,
                item.target_entity_name.casefold(),
            )
            for item in relationships
        }

    expected_entities = {name.casefold() for name in expected.entities}
    expected_relationships = {item.key for item in expected.relationships}
    entity_hit_rate = None
    relationship_hit_rate = None
    path_success = None
    if neighborhood is not None:
        entity_hit_rate = (
            len(found_entities & expected_entities) / len(expected_entities)
            if expected_entities
            else None
        )
        relationship_hit_rate = (
            len(found_relationships & expected_relationships) / len(expected_relationships)
            if expected_relationships
            else None
        )
        if expected.paths:
            successful = sum(
                len(path.relationships) <= neighborhood.depth_used
                and all(step.key in found_relationships for step in path.relationships)
                for path in expected.paths
            )
            path_success = successful / len(expected.paths)

    documents_by_chunk = {item.chunk_id: item for item in corpus}
    relationships_by_key = {item.key: item for item in benchmark_relationships}
    traceability_checks: list[bool] = []
    for item in _deduplicate_evidence(evidence):
        source = documents_by_chunk.get(item.chunk_id)
        traceability_checks.append(
            source is not None
            and source.document_id == item.document_id
            and source.title == item.document_title
        )
    for item in relationships:
        key = (
            item.source_entity_name.casefold(),
            item.relationship_type,
            item.target_entity_name.casefold(),
        )
        expected_source = relationships_by_key.get(key)
        traceability_checks.append(
            expected_source is not None
            and expected_source.source_chunk_id == item.source_chunk_id
            and expected_source.source_document_id == item.source_document_id
        )
    provenance_coverage = (
        sum(traceability_checks) / len(traceability_checks) if traceability_checks else None
    )
    return GraphMetrics(
        entity_hit_rate=entity_hit_rate,
        relationship_hit_rate=relationship_hit_rate,
        path_success=path_success,
        provenance_coverage=provenance_coverage,
    )


def evidence_origin_mix(evidence: Sequence[RetrievedEvidence]) -> dict[RetrievalSource, int]:
    """Count stable unique evidence identities by vector, graph, or both origin."""
    counts: dict[RetrievalSource, int] = {}
    for item in _deduplicate_evidence(evidence):
        counts[item.retrieval_source] = counts.get(item.retrieval_source, 0) + 1
    return counts


def aggregate_case_results(results: Sequence[CaseEvaluationResult]) -> AggregateMetrics:
    """Macro-average supported metrics and sum evidence-origin counts."""
    evaluated = [item for item in results if not item.skipped]
    origins: dict[RetrievalSource, int] = {}
    for result in evaluated:
        for origin, count in result.evidence_origin_mix.items():
            origins[origin] = origins.get(origin, 0) + count
    return AggregateMetrics(
        retrieval=RetrievalMetrics(
            hit_rate_at_k=_average(item.retrieval_metrics.hit_rate_at_k for item in evaluated),
            precision_at_k=_average(item.retrieval_metrics.precision_at_k for item in evaluated),
            recall_at_k=_average(item.retrieval_metrics.recall_at_k for item in evaluated),
            mrr=_average(item.retrieval_metrics.mrr for item in evaluated),
            false_positive_rate=_average(
                item.retrieval_metrics.false_positive_rate for item in evaluated
            ),
        ),
        graph=GraphMetrics(
            entity_hit_rate=_average(item.graph_metrics.entity_hit_rate for item in evaluated),
            relationship_hit_rate=_average(
                item.graph_metrics.relationship_hit_rate for item in evaluated
            ),
            path_success=_average(item.graph_metrics.path_success for item in evaluated),
            provenance_coverage=_average(
                item.graph_metrics.provenance_coverage for item in evaluated
            ),
        ),
        evidence_origin_mix=origins,
    )


def _deduplicate_evidence(evidence: Sequence[RetrievedEvidence]) -> list[RetrievedEvidence]:
    unique = {}
    for item in evidence:
        unique.setdefault(item.chunk_id, item)
    return list(unique.values())


def _average(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None
