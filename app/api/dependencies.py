"""API dependency wiring for application services."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.agents.architecture_agent import OpenAIArchitectureAgent
from app.agents.assessment_agent import OpenAIAssessmentAgent
from app.agents.evidence_agent import OpenAIEvidenceAgent
from app.agents.risk_governance_agent import OpenAIRiskGovernanceAgent
from app.agents.structured_output import StructuredOutput
from app.agents.synthesis_agent import OpenAISynthesisAgent
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.graph.multi_agent_workflow import MultiAgentAssessmentWorkflow
from app.graph.workflow import AgenticAssessmentWorkflow
from app.ingestion.parsers import (
    DOCXDocumentParser,
    MarkdownDocumentParser,
    PDFDocumentParser,
    TextDocumentParser,
)
from app.ingestion.router import DocumentParserRouter
from app.ingestion.service import FileIngestionService
from app.knowledge_graph.enrichment import KnowledgeGraphEnrichmentService
from app.knowledge_graph.extraction import OpenAIEntityExtractor, OpenAIRelationshipExtractor
from app.knowledge_graph.hybrid import HybridRAGService, HybridRetrievalService
from app.knowledge_graph.retrieval import GraphRetrievalService
from app.providers.contracts import EmbeddingProvider, StructuredModelProvider
from app.providers.factory import build_embedding_provider, build_structured_model_provider
from app.rag.ingestion import KnowledgeIngestionService
from app.rag.retrieval import RetrievalService
from app.rag.service import RAGService
from app.repositories.assessments import AssessmentRepository
from app.repositories.knowledge_chunks import KnowledgeChunkRepository
from app.repositories.knowledge_documents import KnowledgeDocumentRepository
from app.repositories.knowledge_graph import KnowledgeGraphRepository
from app.repositories.runtime_reviews import RuntimeReviewRepository
from app.runtime.gate import RuntimeRiskGate
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RuntimeRiskPolicy
from app.services.assessments import AssessmentGenerator, AssessmentService
from app.services.llm import ProviderAssessmentGenerator
from app.services.runtime_governance import RuntimeGovernanceService
from app.tools.knowledge import build_knowledge_tool_registry
from app.tools.permissions import AgentToolPermissions
from app.tools.registry import ToolRegistry


def get_runtime_metrics_recorder() -> RuntimeMetricsRecorder:
    """Create one request-scoped privacy-safe metrics accumulator."""
    return RuntimeMetricsRecorder()


def get_structured_model_provider(
    settings: Annotated[Settings, Depends(get_settings)],
    metrics: Annotated[RuntimeMetricsRecorder, Depends(get_runtime_metrics_recorder)],
) -> StructuredModelProvider:
    """Select one validated built-in structured model adapter."""
    return build_structured_model_provider(settings, metrics=metrics)


def get_assessment_generator(
    provider: Annotated[StructuredModelProvider, Depends(get_structured_model_provider)],
) -> AssessmentGenerator:
    """Build assessment generation over the provider-neutral contract."""
    return ProviderAssessmentGenerator(provider)


def get_assessment_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> AssessmentRepository:
    """Build a repository around the request-scoped database session."""
    return AssessmentRepository(session)


def get_runtime_review_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> RuntimeReviewRepository:
    """Build the durable V7C checkpoint and audit repository."""
    return RuntimeReviewRepository(session)


def get_runtime_governance_service(
    assessments: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    reviews: Annotated[RuntimeReviewRepository, Depends(get_runtime_review_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
    metrics: Annotated[RuntimeMetricsRecorder, Depends(get_runtime_metrics_recorder)],
) -> RuntimeGovernanceService:
    """Build the framework-neutral runtime gate and review coordinator."""
    policy = RuntimeRiskPolicy(
        medium_risk_decision=settings.runtime_medium_risk_decision,
        high_risk_decision=settings.runtime_high_risk_decision,
        critical_risk_decision=settings.runtime_critical_risk_decision,
        review_on_insufficient_evidence=settings.runtime_review_on_insufficient_evidence,
        review_on_degraded_execution=settings.runtime_review_on_degraded_execution,
        review_on_specialist_unavailable=settings.runtime_review_on_specialist_unavailable,
        review_on_tool_failure=settings.runtime_review_on_tool_failure,
        block_high_risk_invalid_provenance=(settings.runtime_block_high_risk_invalid_provenance),
        block_critical_missing_mitigation=(settings.runtime_block_critical_missing_mitigation),
        max_human_revisions=settings.max_human_revisions,
    )
    return RuntimeGovernanceService(
        assessments=assessments,
        reviews=reviews,
        gate=RuntimeRiskGate(policy),
        input_cost_per_million=settings.model_input_cost_per_1m_tokens,
        output_cost_per_million=settings.model_output_cost_per_1m_tokens,
        metrics=metrics,
    )


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


def get_knowledge_graph_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> KnowledgeGraphRepository:
    """Build the V6 relational graph repository on the request-scoped session."""
    return KnowledgeGraphRepository(session)


def get_embeddings_service(
    settings: Annotated[Settings, Depends(get_settings)],
    metrics: Annotated[RuntimeMetricsRecorder, Depends(get_runtime_metrics_recorder)],
) -> EmbeddingProvider:
    """Build the configured embedding adapter independently from chat selection."""
    return build_embedding_provider(settings, metrics=metrics)


def get_knowledge_ingestion_service(
    documents: Annotated[
        KnowledgeDocumentRepository,
        Depends(get_knowledge_document_repository),
    ],
    chunks: Annotated[KnowledgeChunkRepository, Depends(get_knowledge_chunk_repository)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embeddings_service)],
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


def get_file_parser_router(
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentParserRouter:
    """Build the hard-allowlisted V6.5 parser router."""
    return DocumentParserRouter(
        [
            PDFDocumentParser(min_extracted_characters=settings.pdf_min_extracted_characters),
            DOCXDocumentParser(),
            TextDocumentParser(),
            MarkdownDocumentParser(),
        ]
    )


def get_retrieval_service(
    chunks: Annotated[KnowledgeChunkRepository, Depends(get_knowledge_chunk_repository)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embeddings_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RetrievalService:
    """Compose query embeddings with pgvector cosine search."""
    return RetrievalService(
        chunks=chunks,
        embeddings=embeddings,
        top_k=settings.rag_retrieval_top_k,
        similarity_threshold=settings.rag_similarity_threshold,
    )


def get_graph_retrieval_service(
    graph: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GraphRetrievalService | None:
    """Expose bounded graph traversal only behind the explicit V6 feature flag."""
    if not settings.knowledge_graph_enabled:
        return None
    return GraphRetrievalService(
        graph=graph,
        max_depth=settings.graph_max_depth,
        max_entities=settings.graph_max_entities,
        min_confidence=settings.graph_min_confidence,
    )


def get_assessment_rag_service(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    graph: Annotated[GraphRetrievalService | None, Depends(get_graph_retrieval_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RAGService | HybridRAGService | None:
    """Enable assessment retrieval only when explicitly configured."""
    if not settings.rag_enabled:
        return None
    if graph is not None:
        return HybridRAGService(HybridRetrievalService(vector=retrieval, graph=graph))
    return RAGService(retrieval)


def get_graph_structured_output(
    settings: Annotated[Settings, Depends(get_settings)],
    metrics: Annotated[RuntimeMetricsRecorder, Depends(get_runtime_metrics_recorder)],
) -> StructuredOutput:
    """Build the schema-constrained adapter used by per-chunk graph extraction."""
    return StructuredOutput(
        build_structured_model_provider(
            settings,
            metrics=metrics,
            timeout_seconds=settings.graph_extraction_timeout_seconds,
        )
    )


def get_graph_enrichment_service(
    documents: Annotated[
        KnowledgeDocumentRepository,
        Depends(get_knowledge_document_repository),
    ],
    chunks: Annotated[KnowledgeChunkRepository, Depends(get_knowledge_chunk_repository)],
    graph: Annotated[KnowledgeGraphRepository, Depends(get_knowledge_graph_repository)],
    structured: Annotated[StructuredOutput, Depends(get_graph_structured_output)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> KnowledgeGraphEnrichmentService | None:
    """Compose opt-in atomic enrichment over existing V3 document chunks."""
    if not settings.knowledge_graph_enabled:
        return None
    return KnowledgeGraphEnrichmentService(
        documents=documents,
        chunks=chunks,
        graph=graph,
        entity_extractor=OpenAIEntityExtractor(
            structured,
            max_entities=settings.graph_max_entities,
            min_confidence=settings.graph_min_confidence,
        ),
        relationship_extractor=OpenAIRelationshipExtractor(
            structured,
            min_confidence=settings.graph_min_confidence,
        ),
    )


def get_file_ingestion_service(
    parsers: Annotated[DocumentParserRouter, Depends(get_file_parser_router)],
    knowledge: Annotated[
        KnowledgeIngestionService,
        Depends(get_knowledge_ingestion_service),
    ],
    graph: Annotated[
        KnowledgeGraphEnrichmentService | None,
        Depends(get_graph_enrichment_service),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileIngestionService:
    """Adapt validated file content into the existing V3 and optional V6 services."""
    return FileIngestionService(
        parsers=parsers,
        knowledge=knowledge,
        graph=graph,
        max_upload_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
    )


def get_assessment_agent(
    generator: Annotated[AssessmentGenerator, Depends(get_assessment_generator)],
    provider: Annotated[StructuredModelProvider, Depends(get_structured_model_provider)],
) -> OpenAIAssessmentAgent:
    """Build exactly one provider-backed assessment reasoning agent."""
    return OpenAIAssessmentAgent(
        generator=generator,
        provider=provider,
    )


def get_agent_tool_registry(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    documents: Annotated[
        KnowledgeDocumentRepository,
        Depends(get_knowledge_document_repository),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    metrics: Annotated[RuntimeMetricsRecorder, Depends(get_runtime_metrics_recorder)],
) -> ToolRegistry:
    """Expose only the two approved V4 read-only knowledge tools."""
    return build_knowledge_tool_registry(
        retrieval=retrieval,
        documents=documents,
        timeout_seconds=settings.tool_timeout_seconds,
        metrics=metrics,
    )


def get_evidence_tool_registry(
    retrieval: Annotated[RetrievalService, Depends(get_retrieval_service)],
    documents: Annotated[
        KnowledgeDocumentRepository,
        Depends(get_knowledge_document_repository),
    ],
    graph: Annotated[GraphRetrievalService | None, Depends(get_graph_retrieval_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    metrics: Annotated[RuntimeMetricsRecorder, Depends(get_runtime_metrics_recorder)],
) -> ToolRegistry:
    """Preserve V4's registry and add graph search only for the V5 Evidence Agent."""
    return build_knowledge_tool_registry(
        retrieval=retrieval,
        documents=documents,
        graph=graph,
        timeout_seconds=settings.tool_timeout_seconds,
        metrics=metrics,
    )


def get_agentic_assessment_workflow(
    agent: Annotated[OpenAIAssessmentAgent, Depends(get_assessment_agent)],
    tools: Annotated[ToolRegistry, Depends(get_agent_tool_registry)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AgenticAssessmentWorkflow | None:
    """Compile the V4 graph only when the explicit feature flag is enabled."""
    if not settings.agentic_workflow_enabled or settings.multi_agent_workflow_enabled:
        return None
    return AgenticAssessmentWorkflow(
        agent=agent,
        tools=tools,
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        recursion_limit=settings.langgraph_recursion_limit,
    )


def get_multi_agent_structured_output(
    provider: Annotated[StructuredModelProvider, Depends(get_structured_model_provider)],
) -> StructuredOutput:
    """Build the shared provider adapter; each specialist still has its own prompt and contract."""
    return StructuredOutput(provider)


def get_evidence_agent(
    tools: Annotated[ToolRegistry, Depends(get_evidence_tool_registry)],
    settings: Annotated[Settings, Depends(get_settings)],
    provider: Annotated[StructuredModelProvider, Depends(get_structured_model_provider)],
) -> OpenAIEvidenceAgent:
    """Build the only V5 specialist allowed to receive tool schemas."""
    return OpenAIEvidenceAgent(
        tools=tools,
        permissions=AgentToolPermissions(),
        max_steps=settings.evidence_agent_max_steps,
        max_tool_calls=settings.evidence_agent_max_tool_calls,
        store_responses=settings.openai_store_responses,
        retry_limit=settings.provider_max_retries,
        retry_base_delay_ms=settings.provider_retry_base_delay_ms,
        timeout_seconds=settings.model_timeout_seconds,
        provider=provider,
    )


def get_architecture_agent(
    structured: Annotated[StructuredOutput, Depends(get_multi_agent_structured_output)],
) -> OpenAIArchitectureAgent:
    """Build the tool-free architecture specialist."""
    return OpenAIArchitectureAgent(structured)


def get_risk_governance_agent(
    structured: Annotated[StructuredOutput, Depends(get_multi_agent_structured_output)],
) -> OpenAIRiskGovernanceAgent:
    """Build the tool-free risk and governance specialist."""
    return OpenAIRiskGovernanceAgent(structured)


def get_synthesis_agent(
    structured: Annotated[StructuredOutput, Depends(get_multi_agent_structured_output)],
) -> OpenAISynthesisAgent:
    """Build the tool-free final synthesis specialist."""
    return OpenAISynthesisAgent(structured)


def get_multi_agent_assessment_workflow(
    evidence: Annotated[OpenAIEvidenceAgent, Depends(get_evidence_agent)],
    architecture: Annotated[OpenAIArchitectureAgent, Depends(get_architecture_agent)],
    risk_governance: Annotated[
        OpenAIRiskGovernanceAgent,
        Depends(get_risk_governance_agent),
    ],
    synthesis: Annotated[OpenAISynthesisAgent, Depends(get_synthesis_agent)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MultiAgentAssessmentWorkflow | None:
    """Compile V5 only when its higher-precedence feature flag is enabled."""
    if not settings.multi_agent_workflow_enabled:
        return None
    return MultiAgentAssessmentWorkflow(
        evidence=evidence,
        architecture=architecture,
        risk_governance=risk_governance,
        synthesis=synthesis,
        max_failures=settings.multi_agent_max_failures,
    )


def get_assessment_service(
    generator: Annotated[AssessmentGenerator, Depends(get_assessment_generator)],
    repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
    rag_service: Annotated[
        RAGService | HybridRAGService | None,
        Depends(get_assessment_rag_service),
    ],
    agentic_workflow: Annotated[
        AgenticAssessmentWorkflow | None,
        Depends(get_agentic_assessment_workflow),
    ],
    multi_agent_workflow: Annotated[
        MultiAgentAssessmentWorkflow | None,
        Depends(get_multi_agent_assessment_workflow),
    ],
    runtime_governance: Annotated[
        RuntimeGovernanceService, Depends(get_runtime_governance_service)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssessmentService:
    """Compose the service from provider and persistence boundaries."""
    return AssessmentService(
        generator,
        repository,
        rag_service,
        agentic_workflow=agentic_workflow,
        multi_agent_workflow=multi_agent_workflow,
        runtime_governance=(runtime_governance if settings.runtime_risk_gate_enabled else None),
    )
