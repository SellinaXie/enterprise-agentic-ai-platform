"""API dependency wiring for application services."""

from functools import partial
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents.assessment_agent import OpenAIAssessmentAgent
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.graph.workflow import AgenticAssessmentWorkflow
from app.rag.embeddings import OpenAIEmbeddingsService
from app.rag.ingestion import KnowledgeIngestionService
from app.rag.retrieval import RetrievalService
from app.rag.service import RAGService
from app.repositories.assessments import AssessmentRepository
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.services.assessments import AssessmentGenerator, AssessmentService
from app.services.llm import OpenAIAssessmentGenerator, get_openai_client
from app.tools.knowledge import build_knowledge_tool_registry
from app.tools.registry import ToolRegistry


def get_assessment_generator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssessmentGenerator:
    """Build the structured generator with a lazily created OpenAI client."""
    return OpenAIAssessmentGenerator(
        model=settings.openai_model,
        store_responses=settings.openai_store_responses,
        client_provider=partial(get_openai_client, settings),
    )


def get_assessment_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> AssessmentRepository:
    """Build a repository around the request-scoped database session."""
    return AssessmentRepository(session)


def get_knowledge_document_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> KnowledgeDocumentRepository:
    """Build a document repository around the request-scoped session."""
    return KnowledgeDocumentRepository(session)


def get_knowledge_chunk_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> KnowledgeChunkRepository:
    """Build a chunk repository around the request-scoped session."""
    return KnowledgeChunkRepository(session)


def get_embeddings_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> OpenAIEmbeddingsService:
    """Build the dimension-constrained OpenAI embeddings adapter."""
    return OpenAIEmbeddingsService(
        model=settings.openai_embedding_model,
        dimension=settings.openai_embedding_dimension,
        client_provider=partial(get_openai_client, settings),
    )


def get_knowledge_ingestion_service(
    documents: Annotated[
        KnowledgeDocumentRepository,
        Depends(get_knowledge_document_repository),
    ],
    chunks: Annotated[KnowledgeChunkRepository, Depends(get_knowledge_chunk_repository)],
    embeddings: Annotated[OpenAIEmbeddingsService, Depends(get_embeddings_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> KnowledgeIngestionService:
    """Compose the plain-text knowledge ingestion pipeline."""
    return KnowledgeIngestionService(
        documents=documents,
        chunks=chunks,
        embeddings=embeddings,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
    )


def get_retrieval_service(
    chunks: Annotated[KnowledgeChunkRepository, Depends(get_knowledge_chunk_repository)],
    embeddings: Annotated[OpenAIEmbeddingsService, Depends(get_embeddings_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RetrievalService:
    """Compose query embeddings with pgvector cosine search."""
    return RetrievalService(
        chunks=chunks,
        embeddings=embeddings,
        top_k=settings.rag_retrieval_top_k,
        similarity_threshold=settings.rag_similarity_threshold,
    )


def get_assessment_rag_service(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RAGService | None:
    """Enable assessment retrieval only when explicitly configured."""
    return RAGService(retrieval) if settings.rag_enabled else None


def get_assessment_agent(
    generator: Annotated[AssessmentGenerator, Depends(get_assessment_generator)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> OpenAIAssessmentAgent:
    """Build exactly one OpenAI-backed assessment reasoning agent."""
    return OpenAIAssessmentAgent(
        model=settings.openai_model,
        generator=generator,
        store_responses=settings.openai_store_responses,
        client_provider=partial(get_openai_client, settings),
    )


def get_agent_tool_registry(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    documents: Annotated[
        KnowledgeDocumentRepository,
        Depends(get_knowledge_document_repository),
    ],
) -> ToolRegistry:
    """Expose only the two approved V4 read-only knowledge tools."""
    return build_knowledge_tool_registry(retrieval=retrieval, documents=documents)


def get_agentic_assessment_workflow(
    agent: Annotated[OpenAIAssessmentAgent, Depends(get_assessment_agent)],
    tools: Annotated[ToolRegistry, Depends(get_agent_tool_registry)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgenticAssessmentWorkflow | None:
    """Compile the V4 graph only when the explicit feature flag is enabled."""
    if not settings.agentic_workflow_enabled:
        return None
    return AgenticAssessmentWorkflow(
        agent=agent,
        tools=tools,
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        recursion_limit=settings.langgraph_recursion_limit,
    )


def get_assessment_service(
    generator: Annotated[AssessmentGenerator, Depends(get_assessment_generator)],
    repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    rag_service: Annotated[RAGService | None, Depends(get_assessment_rag_service)],
    agentic_workflow: Annotated[
        AgenticAssessmentWorkflow | None,
        Depends(get_agentic_assessment_workflow),
    ],
) -> AssessmentService:
    """Compose the service from provider and persistence boundaries."""
    return AssessmentService(
        generator,
        repository,
        rag_service,
        agentic_workflow=agentic_workflow,
    )
