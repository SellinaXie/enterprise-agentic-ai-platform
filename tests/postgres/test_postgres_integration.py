"""Live verification of the V2-V4 persistence and V3 pgvector layers."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from openai import OpenAI
from pgvector.sqlalchemy import VECTOR
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Session, sessionmaker

from app.api.dependencies import get_assessment_generator, get_embeddings_service
from app.core.config import Settings
from app.db.models.assessment import AssessmentModel
from app.main import create_app
from app.models.assessment import AssessmentStatus, ExternalEvidenceStatus
from app.rag.ingestion import KnowledgeIngestionService
from app.rag.retrieval import RetrievalService
from app.repositories.assessments import AssessmentRepository
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.schemas.assessment import (
    AssessmentRequest,
    AssessmentResponse,
    AssessmentResult,
    SourceReference,
)
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.services.llm import OpenAIAssessmentGenerator
from tests.knowledge_fixtures import DeterministicEmbeddingsService

pytestmark = pytest.mark.postgres


def _create(repository: AssessmentRepository, request: AssessmentRequest) -> UUID:
    assessment_id = uuid4()
    repository.create(
        assessment_id=assessment_id,
        company_name=request.company_name,
        industry=request.industry,
        business_problem=request.business_problem,
        request_payload=request.model_dump(mode="json"),
    )
    repository.commit()
    return assessment_id


def test_connection_migration_and_native_schema(postgres_engine: Engine) -> None:
    """Verify the server, Alembic head, table, and native PostgreSQL column types."""
    with postgres_engine.connect() as connection:
        version = connection.execute(text("SELECT version()")).scalar_one()
        revision = MigrationContext.configure(connection).get_current_revision()

    schema = inspect(postgres_engine)
    columns = {column["name"]: column for column in schema.get_columns("assessments")}
    knowledge_columns = {
        column["name"]: column for column in schema.get_columns("knowledge_chunks")
    }
    knowledge_indexes = {index["name"] for index in schema.get_indexes("knowledge_chunks")}
    with postgres_engine.connect() as connection:
        vector_version = connection.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()

    assert version.startswith("PostgreSQL ")
    assert revision == "20260910_0005"
    assert "assessments" in schema.get_table_names()
    assert "knowledge_documents" in schema.get_table_names()
    assert "knowledge_chunks" in schema.get_table_names()
    assert "assessment_runtime_states" in schema.get_table_names()
    assert "human_review_events" in schema.get_table_names()
    assert vector_version
    assert isinstance(columns["id"]["type"], PostgreSQLUUID)
    assert isinstance(columns["request_payload"]["type"], JSONB)
    assert isinstance(columns["result_payload"]["type"], JSONB)
    assert isinstance(columns["execution_metadata"]["type"], JSONB)
    assert isinstance(columns["created_at"]["type"], TIMESTAMP)
    assert columns["created_at"]["type"].timezone is True
    assert columns["updated_at"]["type"].timezone is True
    assert columns["completed_at"]["type"].timezone is True
    assert isinstance(knowledge_columns["embedding"]["type"], VECTOR)
    assert knowledge_columns["embedding"]["type"].dim == 1536
    assert "ix_knowledge_chunks_embedding_hnsw" in knowledge_indexes


def test_readiness_passes_against_migrated_postgres(
    postgres_database_url: str,
    postgres_engine: Engine,
) -> None:
    """Readiness verifies connectivity and the complete migration head without provider I/O."""
    del postgres_engine
    application = create_app(
        Settings(
            _env_file=None,
            APP_ENV="test",
            APP_LOG_LEVEL="ERROR",
            DATABASE_URL=postgres_database_url,
            OPENAI_API_KEY=None,
            PROVIDER_REQUIRED=False,
        )
    )

    with TestClient(application) as client:
        response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ready", "schema": "ready", "configuration": "ready"},
    }
    assert postgres_database_url not in response.text


def test_pgvector_knowledge_ingestion_and_similarity_search(
    postgres_session_factory: sessionmaker[Session],
    synthetic_knowledge_corpus: list[KnowledgeDocumentCreate],
) -> None:
    """Persist synthetic JSONB/vector data and retrieve the nearest compliance source."""
    embeddings = DeterministicEmbeddingsService(dimension=1536)
    with postgres_session_factory() as session:
        documents = KnowledgeDocumentRepository(session)
        chunks = KnowledgeChunkRepository(session)
        ingestion = KnowledgeIngestionService(
            documents=documents,
            chunks=chunks,
            embeddings=embeddings,
            chunk_size=1_200,
            chunk_overlap=200,
        )
        ingested = [ingestion.ingest(document) for document in synthetic_knowledge_corpus]
        retrieval = RetrievalService(
            chunks=chunks,
            embeddings=embeddings,
            top_k=3,
            similarity_threshold=0.5,
        )
        results = retrieval.search("compliance review for regulated lending")
        stored_chunks = chunks.list_by_document(ingested[1].document.document_id)

    assert results
    assert results[0].document_title == "Synthetic Financial Services Compliance Workflow"
    assert results[0].metadata["document"] == {"topic": "compliance", "synthetic": True}
    assert len({result.chunk_id for result in results}) == len(results)
    assert len(stored_chunks[0].embedding) == 1536
    assert stored_chunks[0].metadata["content_hash"]


def test_repository_create_get_and_completed_round_trip(
    postgres_session_factory: sessionmaker[Session],
    synthetic_assessment_request: AssessmentRequest,
    synthetic_assessment_result: AssessmentResult,
) -> None:
    """Round-trip UUID, JSONB, timestamps, status updates, and a completed result."""
    request = synthetic_assessment_request
    expected_result = synthetic_assessment_result
    execution_metadata = {
        "execution_mode": "agentic",
        "steps_used": 1,
        "tools_used": [],
        "termination_reason": "agent_stopped",
        "trace": [],
    }

    with postgres_session_factory() as session:
        repository = AssessmentRepository(session)
        assessment_id = _create(repository, request)
        pending = repository.get_by_id(assessment_id)
        processing = repository.mark_processing(assessment_id)
        repository.commit()
        completed = repository.mark_completed(
            assessment_id,
            expected_result.model_dump(mode="json"),
            execution_metadata,
        )
        repository.commit()

    with postgres_session_factory() as session:
        persisted = AssessmentRepository(session).get_by_id(assessment_id)

    assert pending is not None
    assert pending.assessment_id == assessment_id
    assert isinstance(pending.assessment_id, UUID)
    assert pending.status == AssessmentStatus.PENDING
    assert pending.request_payload == request.model_dump(mode="json")
    assert pending.created_at.utcoffset() is not None
    assert pending.updated_at.utcoffset() is not None
    assert processing is not None and processing.status == AssessmentStatus.PROCESSING
    assert completed is not None and completed.status == AssessmentStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.completed_at.utcoffset() is not None
    assert persisted is not None
    assert persisted.status == AssessmentStatus.COMPLETED
    assert AssessmentResult.model_validate(persisted.result_payload) == expected_result
    assert persisted.execution_metadata == execution_metadata


def test_repository_failed_state_round_trip(
    postgres_session_factory: sessionmaker[Session],
    synthetic_assessment_request: AssessmentRequest,
) -> None:
    """Persist a safe failed lifecycle state without a result or completion timestamp."""
    with postgres_session_factory() as session:
        repository = AssessmentRepository(session)
        assessment_id = _create(repository, synthetic_assessment_request)
        repository.mark_processing(assessment_id)
        repository.commit()
        repository.mark_failed(
            assessment_id,
            error_code="llm_provider_error",
            error_message="AI assessment generation is temporarily unavailable. Please try again.",
        )
        repository.commit()

    with postgres_session_factory() as session:
        failed = AssessmentRepository(session).get_by_id(assessment_id)

    assert failed is not None
    assert failed.status == AssessmentStatus.FAILED
    assert failed.result_payload is None
    assert failed.error_code == "llm_provider_error"
    assert failed.error_message == (
        "AI assessment generation is temporarily unavailable. Please try again."
    )
    assert failed.completed_at is None
    assert failed.updated_at.utcoffset() is not None


def test_postgres_constraints_accept_independent_rows(
    postgres_session_factory: sessionmaker[Session],
    synthetic_assessment_request: AssessmentRequest,
) -> None:
    """Create unrelated records to demonstrate order-independent repository behavior."""
    first_id = uuid4()
    second_id = uuid4()
    request_payload = synthetic_assessment_request.model_dump(mode="json")

    with postgres_session_factory() as session:
        repository = AssessmentRepository(session)
        for assessment_id in (first_id, second_id):
            repository.create(
                assessment_id=assessment_id,
                company_name=request_payload["company_name"],
                industry=request_payload["industry"],
                business_problem=request_payload["business_problem"],
                request_payload=request_payload,
            )
        repository.commit()
        stored_ids = set(session.scalars(select(AssessmentModel.id)).all())

    assert stored_ids == {first_id, second_id}


def test_api_create_and_get_with_mocked_openai(
    postgres_database_url: str,
    postgres_engine: Engine,
    postgres_session_factory: sessionmaker[Session],
    synthetic_assessment_request: AssessmentRequest,
    synthetic_assessment_result: AssessmentResult,
    synthetic_knowledge_corpus: list[KnowledgeDocumentCreate],
) -> None:
    """Exercise grounded POST/GET with real pgvector and mocked OpenAI calls."""
    del postgres_engine
    embeddings = DeterministicEmbeddingsService(dimension=1536)
    with postgres_session_factory() as session:
        documents = KnowledgeDocumentRepository(session)
        chunks = KnowledgeChunkRepository(session)
        ingested = KnowledgeIngestionService(
            documents=documents,
            chunks=chunks,
            embeddings=embeddings,
            chunk_size=1_200,
            chunk_overlap=200,
        ).ingest(synthetic_knowledge_corpus[1])
        chunk = chunks.list_by_document(ingested.document.document_id)[0]

    expected_result = synthetic_assessment_result.model_copy(
        update={
            "external_evidence_status": ExternalEvidenceStatus.RETRIEVED,
            "source_references": [
                SourceReference(
                    document_id=ingested.document.document_id,
                    chunk_id=chunk.chunk_id,
                    document_title=ingested.document.title,
                )
            ],
        }
    )
    openai_client = Mock()
    openai_client.responses.parse.return_value = SimpleNamespace(output_parsed=expected_result)
    generator = OpenAIAssessmentGenerator(
        model="gpt-4.1-mini",
        client_provider=lambda: cast(OpenAI, openai_client),
    )
    settings = Settings(
        _env_file=None,
        APP_ENV="test",
        APP_LOG_LEVEL="ERROR",
        DATABASE_URL=postgres_database_url,
        OPENAI_API_KEY=None,
        RAG_ENABLED=True,
    )
    application = create_app(settings)
    application.dependency_overrides[get_assessment_generator] = lambda: generator
    application.dependency_overrides[get_embeddings_service] = lambda: embeddings

    with TestClient(application) as client:
        created_response = client.post(
            "/api/v1/assessments",
            json=synthetic_assessment_request.model_dump(mode="json"),
        )
        assert created_response.status_code == 200
        created = AssessmentResponse.model_validate(created_response.json())

        retrieved_response = client.get(f"/api/v1/assessments/{created.assessment_id}")
        assert retrieved_response.status_code == 200
        retrieved = AssessmentResponse.model_validate(retrieved_response.json())

    assert created.status == AssessmentStatus.COMPLETED
    assert created.result == expected_result
    assert retrieved == created
    openai_client.responses.parse.assert_called_once()
