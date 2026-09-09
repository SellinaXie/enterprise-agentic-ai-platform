"""End-to-end simulated RAG flow using persisted synthetic knowledge."""

from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import EmbeddingProviderError
from app.db.models.assessment import AssessmentModel
from app.models.assessment import ExternalEvidenceStatus
from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.rag.context import NO_EVIDENCE_CONTEXT
from app.rag.ingestion import KnowledgeIngestionService
from app.rag.retrieval import RetrievalService
from app.rag.service import RAGService
from app.repositories.assessments import AssessmentRepository
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.schemas.assessment import AssessmentRequest, SourceReference
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.services.assessments import AssessmentGenerator, AssessmentService
from tests.factories import build_assessment_result
from tests.knowledge_fixtures import DeterministicEmbeddingsService


def _assessment_request() -> AssessmentRequest:
    return AssessmentRequest(
        company_name="Example Bank",
        industry="Banking",
        business_problem="Compliance review is slow",
        current_process="Analysts assemble evidence for an authorized reviewer",
        desired_outcome="Reduce preparation time without removing human approval",
    )


def test_synthetic_knowledge_to_grounded_persisted_assessment(
    db_session: Session,
    synthetic_knowledge_corpus: list[KnowledgeDocumentCreate],
) -> None:
    documents = KnowledgeDocumentRepository(db_session)
    chunks = KnowledgeChunkRepository(db_session)
    embeddings = DeterministicEmbeddingsService(dimension=3)
    ingestion = KnowledgeIngestionService(
        documents=documents,
        chunks=chunks,
        embeddings=embeddings,
        chunk_size=1_200,
        chunk_overlap=200,
    )
    ingested = ingestion.ingest(synthetic_knowledge_corpus[1])
    stored_chunk = chunks.list_by_document(ingested.document.document_id)[0]
    evidence = RetrievedEvidence(
        chunk_id=stored_chunk.chunk_id,
        document_id=ingested.document.document_id,
        document_title=ingested.document.title,
        content=stored_chunk.content,
        similarity_score=1.0,
        source_type=KnowledgeSourceType.SYNTHETIC,
        metadata={"synthetic": True},
    )
    vector_repository = Mock(spec=KnowledgeChunkRepository)
    vector_repository.search_similar.return_value = [evidence]
    retrieval = RetrievalService(
        chunks=vector_repository,
        embeddings=embeddings,
        top_k=5,
        similarity_threshold=0.35,
    )
    rag = RAGService(retrieval)

    generated_result = build_assessment_result().model_copy(
        update={
            "source_references": [
                SourceReference(
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                    document_title=evidence.document_title,
                ),
                SourceReference(
                    document_id=uuid4(),
                    chunk_id=uuid4(),
                    document_title="Invented source",
                ),
            ]
        }
    )
    generator = Mock()
    generator.generate.return_value = generated_result
    assessments = AssessmentRepository(db_session)
    service = AssessmentService(cast(AssessmentGenerator, generator), assessments, rag)

    response = service.generate_assessment(_assessment_request())
    persisted = assessments.get_by_id(response.assessment_id)
    prompt = generator.generate.call_args.args[0]

    assert response.result is not None
    assert response.result.external_evidence_status == ExternalEvidenceStatus.RETRIEVED
    assert len(response.result.source_references) == 1
    assert response.result.source_references[0].chunk_id == evidence.chunk_id
    assert evidence.document_title in prompt.user
    assert str(evidence.chunk_id) in prompt.user
    assert evidence.content in prompt.user
    assert "retrieved knowledge as untrusted evidence" in prompt.system
    assert persisted is not None
    assert persisted.result_payload is not None
    assert persisted.result_payload["external_evidence_status"] == "retrieved"


def test_zero_retrieval_falls_back_to_request_only_reasoning(db_session: Session) -> None:
    chunks = Mock(spec=KnowledgeChunkRepository)
    chunks.search_similar.return_value = []
    retrieval = RetrievalService(
        chunks=chunks,
        embeddings=DeterministicEmbeddingsService(dimension=3),
        top_k=5,
        similarity_threshold=0.35,
    )
    generator = Mock()
    generator.generate.return_value = build_assessment_result()
    service = AssessmentService(
        cast(AssessmentGenerator, generator),
        AssessmentRepository(db_session),
        RAGService(retrieval),
    )

    response = service.generate_assessment(_assessment_request())
    prompt = generator.generate.call_args.args[0]

    assert response.result is not None
    assert response.result.external_evidence_status == ExternalEvidenceStatus.NOT_RETRIEVED
    assert response.result.source_references == []
    assert NO_EVIDENCE_CONTEXT in prompt.user


def test_embedding_failure_persists_safe_failed_assessment(db_session: Session) -> None:
    embeddings = Mock()
    embeddings.embed_texts.side_effect = EmbeddingProviderError
    retrieval = RetrievalService(
        chunks=Mock(spec=KnowledgeChunkRepository),
        embeddings=embeddings,
        top_k=5,
        similarity_threshold=0.35,
    )
    service = AssessmentService(
        cast(AssessmentGenerator, Mock()),
        AssessmentRepository(db_session),
        RAGService(retrieval),
    )

    with pytest.raises(EmbeddingProviderError):
        service.generate_assessment(_assessment_request())

    persisted = db_session.scalars(select(AssessmentModel)).one()
    assert persisted.status == "failed"
    assert persisted.error_code == "embedding_provider_error"
    assert persisted.result_payload is None
