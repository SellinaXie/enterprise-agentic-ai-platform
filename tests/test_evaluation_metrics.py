"""Deterministic V7A ranked, graph, negative, and provenance metric tests."""

from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from app.evaluation.dataset import load_evaluation_dataset
from app.evaluation.fixtures import DeterministicGraphRetrieval, DeterministicVectorRetrieval
from app.evaluation.metrics import calculate_graph_metrics, calculate_retrieval_metrics
from app.evaluation.models import EvaluationExpectedEvidence
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence


def _evidence(
    chunk_id: UUID,
    document_id: UUID,
    *,
    title: str = "Synthetic",
) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id=chunk_id,
        document_id=document_id,
        document_title=title,
        content="Synthetic evidence",
        similarity_score=1.0,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )


def test_ranked_metrics_perfect_retrieval() -> None:
    document_ids = [uuid4(), uuid4()]
    chunk_ids = [uuid4(), uuid4()]
    evidence = [_evidence(chunk_ids[index], document_ids[index]) for index in range(2)]
    expected = EvaluationExpectedEvidence(document_ids=document_ids, chunk_ids=chunk_ids)

    metrics = calculate_retrieval_metrics(evidence, expected, k=2, negative=False)

    assert metrics.hit_rate_at_k == 1.0
    assert metrics.precision_at_k == 1.0
    assert metrics.recall_at_k == 1.0
    assert metrics.mrr == 1.0


def test_ranked_metrics_partial_retrieval_and_first_relevant_rank() -> None:
    expected_chunks = [uuid4(), uuid4()]
    evidence = [
        _evidence(uuid4(), uuid4()),
        _evidence(expected_chunks[0], uuid4()),
    ]
    expected = EvaluationExpectedEvidence(chunk_ids=expected_chunks)

    metrics = calculate_retrieval_metrics(evidence, expected, k=3, negative=False)

    assert metrics.hit_rate_at_k == 1.0
    assert metrics.precision_at_k == pytest.approx(1 / 3)
    assert metrics.recall_at_k == 0.5
    assert metrics.mrr == 0.5


def test_ranked_metrics_no_results_and_no_relevant_items() -> None:
    positive = calculate_retrieval_metrics(
        [],
        EvaluationExpectedEvidence(chunk_ids=[uuid4()]),
        k=5,
        negative=False,
    )
    undefined = calculate_retrieval_metrics(
        [],
        EvaluationExpectedEvidence(),
        k=5,
        negative=False,
    )

    assert positive.hit_rate_at_k == 0.0
    assert positive.precision_at_k == 0.0
    assert positive.recall_at_k == 0.0
    assert positive.mrr == 0.0
    assert undefined.hit_rate_at_k is None


def test_ranked_metrics_deduplicate_results_and_use_fixed_k_denominator() -> None:
    relevant = _evidence(uuid4(), uuid4())
    expected = EvaluationExpectedEvidence(chunk_ids=[relevant.chunk_id, uuid4()])

    metrics = calculate_retrieval_metrics(
        [relevant, relevant],
        expected,
        k=5,
        negative=False,
    )

    assert metrics.precision_at_k == 0.2
    assert metrics.recall_at_k == 0.5
    assert metrics.mrr == 1.0


def test_duplicate_inside_top_k_does_not_promote_a_later_result() -> None:
    first = _evidence(uuid4(), uuid4())
    later = _evidence(uuid4(), uuid4())
    expected = EvaluationExpectedEvidence(chunk_ids=[first.chunk_id, later.chunk_id])

    metrics = calculate_retrieval_metrics(
        [first, first, later],
        expected,
        k=2,
        negative=False,
    )

    assert metrics.precision_at_k == 0.5
    assert metrics.recall_at_k == 0.5


def test_negative_query_false_positive_rate_penalizes_any_result() -> None:
    expected = EvaluationExpectedEvidence()

    empty = calculate_retrieval_metrics([], expected, k=5, negative=True)
    false_positive = calculate_retrieval_metrics(
        [_evidence(uuid4(), uuid4())],
        expected,
        k=5,
        negative=True,
    )

    assert empty.false_positive_rate == 0.0
    assert false_positive.false_positive_rate == 1.0
    assert false_positive.hit_rate_at_k is None


def test_graph_metrics_cover_entities_relationships_paths_and_provenance() -> None:
    dataset = load_evaluation_dataset()
    case = dataset.cases[1]
    neighborhood = DeterministicGraphRetrieval(dataset).search(case.query)

    metrics = calculate_graph_metrics(
        neighborhood,
        neighborhood.evidence,
        case.expected,
        dataset.documents,
        dataset.relationships,
    )

    assert metrics.entity_hit_rate == 1.0
    assert metrics.relationship_hit_rate == 1.0
    assert metrics.path_success == 1.0
    assert metrics.provenance_coverage == 1.0


def test_invented_evidence_identity_fails_provenance_without_affecting_rank_metrics() -> None:
    dataset = load_evaluation_dataset()
    case = dataset.cases[0]
    evidence = DeterministicVectorRetrieval(dataset).search(case.query)
    invented = replace(evidence[0], chunk_id=uuid4(), document_id=uuid4())

    metrics = calculate_graph_metrics(
        None,
        [invented],
        case.expected,
        dataset.documents,
        dataset.relationships,
    )

    assert metrics.provenance_coverage == 0.0
    assert metrics.entity_hit_rate is None
    assert metrics.relationship_hit_rate is None
    assert metrics.path_success is None


def test_invented_relationship_source_cannot_pass_provenance() -> None:
    dataset = load_evaluation_dataset()
    case = dataset.cases[0]
    neighborhood = DeterministicGraphRetrieval(dataset).search(case.query)
    relationships = list(neighborhood.relationships)
    relationships[0] = relationships[0].model_copy(update={"source_chunk_id": uuid4()})
    tampered = neighborhood.model_copy(update={"relationships": relationships})

    metrics = calculate_graph_metrics(
        tampered,
        tampered.evidence,
        case.expected,
        dataset.documents,
        dataset.relationships,
    )

    assert metrics.relationship_hit_rate == 1.0
    assert metrics.provenance_coverage == 0.75
