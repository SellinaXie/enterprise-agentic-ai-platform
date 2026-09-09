"""Retrieval query, ranking boundary, context, and schema tests."""

from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy.exc import ProgrammingError

from app.core.exceptions import KnowledgeStoreUnavailableError
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.rag.context import NO_EVIDENCE_CONTEXT, build_rag_context
from app.rag.retrieval import RetrievalService, build_retrieval_query
from app.schemas.assessment import AssessmentRequest
from app.schemas.knowledge import KnowledgeSearchResponse, RetrievedEvidenceResponse
from tests.knowledge_fixtures import DeterministicEmbeddingsService


def _evidence(score: float = 0.91) -> RetrievedEvidence:
    return RetrievedEvidence(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Synthetic Compliance Workflow",
        content="An authorized reviewer inspects supporting evidence.",
        similarity_score=score,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )


def test_retrieval_query_uses_only_deterministic_assessment_fields() -> None:
    request = AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Compliance review is slow",
        desired_outcome="Reduce turnaround time",
        constraints=["Human approval is required"],
    )

    query = build_retrieval_query(request)

    assert query == (
        "Company: Example Bank\n"
        "Industry: Banking\n"
        "Business problem: Compliance review is slow\n"
        "Desired outcome: Reduce turnaround time\n"
        "Constraints: Human approval is required"
    )


def test_retrieval_forwards_rank_filters_and_preserves_sources() -> None:
    expected = [_evidence()]
    chunks = Mock()
    chunks.search_similar.return_value = expected
    embeddings = DeterministicEmbeddingsService(dimension=3)
    service = RetrievalService(
        chunks=chunks,
        embeddings=embeddings,
        top_k=5,
        similarity_threshold=0.35,
    )

    results = service.search("compliance review", top_k=2)

    assert results == expected
    chunks.search_similar.assert_called_once_with(
        embeddings.embed_texts(["compliance review"])[0],
        limit=2,
        similarity_threshold=0.35,
        source_type=None,
        document_id=None,
    )


def test_rag_context_has_structured_source_boundaries() -> None:
    evidence = _evidence()

    context = build_rag_context([evidence])

    assert "EXTERNAL_KNOWLEDGE_STATUS: RELEVANT_EVIDENCE_RETRIEVED" in context
    assert "BEGIN_SOURCE_1" in context
    assert evidence.document_title in context
    assert str(evidence.document_id) in context
    assert str(evidence.chunk_id) in context
    assert evidence.content in context


def test_zero_retrieval_has_explicit_fallback_context() -> None:
    assert build_rag_context([]) == NO_EVIDENCE_CONTEXT


def test_low_score_and_duplicate_chunks_are_filtered() -> None:
    high = _evidence(0.88)
    low = _evidence(0.20)
    chunks = Mock()
    chunks.search_similar.return_value = [low, high, high]
    service = RetrievalService(
        chunks=chunks,
        embeddings=DeterministicEmbeddingsService(dimension=3),
        top_k=5,
        similarity_threshold=0.35,
    )

    assert service.search("compliance") == [high]


def test_pgvector_query_failure_rolls_back_and_becomes_safe_error() -> None:
    chunks = Mock()
    chunks.search_similar.side_effect = ProgrammingError(
        "vector query",
        {},
        Exception("vector extension unavailable"),
    )
    service = RetrievalService(
        chunks=chunks,
        embeddings=DeterministicEmbeddingsService(dimension=3),
        top_k=5,
        similarity_threshold=0.35,
    )

    with pytest.raises(KnowledgeStoreUnavailableError):
        service.search("compliance")

    chunks.rollback.assert_called_once_with()


def test_retrieval_response_schema_preserves_attribution() -> None:
    item = _evidence()
    response = KnowledgeSearchResponse(results=[RetrievedEvidenceResponse.model_validate(item)])

    assert response.results[0].chunk_id == item.chunk_id
    assert response.results[0].document_title == item.document_title
    assert response.results[0].metadata == {"synthetic": True}
