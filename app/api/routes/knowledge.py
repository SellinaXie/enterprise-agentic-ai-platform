"""Plain-text knowledge ingestion and semantic-search endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    get_graph_enrichment_service,
    get_knowledge_ingestion_service,
    get_retrieval_service,
)
from app.core.exceptions import KnowledgeGraphDisabledError
from app.knowledge_graph.enrichment import KnowledgeGraphEnrichmentService
from app.rag.ingestion import KnowledgeIngestionService
from app.rag.retrieval import RetrievalService
from app.schemas.errors import ErrorResponse
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentResponse,
    KnowledgeIngestionResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    RetrievedEvidenceResponse,
)
from app.schemas.knowledge_graph import KnowledgeGraphEnrichmentResponse

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post(
    "/documents",
    response_model=KnowledgeIngestionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Ingest a plain-text knowledge document",
)
def ingest_document(
    request: KnowledgeDocumentCreate,
    service: Annotated[KnowledgeIngestionService, Depends(get_knowledge_ingestion_service)],
) -> KnowledgeIngestionResponse:
    result = service.ingest(request)
    return KnowledgeIngestionResponse(
        document=KnowledgeDocumentResponse.model_validate(result.document),
        chunk_count=result.chunk_count,
    )


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Retrieve a knowledge document",
)
def get_document(
    document_id: UUID,
    service: Annotated[KnowledgeIngestionService, Depends(get_knowledge_ingestion_service)],
) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse.model_validate(service.get_document(document_id))


@router.post(
    "/documents/{document_id}/graph",
    response_model=KnowledgeGraphEnrichmentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Extract a relational knowledge graph from one existing document",
)
def enrich_document_graph(
    document_id: UUID,
    service: Annotated[
        KnowledgeGraphEnrichmentService | None,
        Depends(get_graph_enrichment_service),
    ],
) -> KnowledgeGraphEnrichmentResponse:
    if service is None:
        raise KnowledgeGraphDisabledError
    return KnowledgeGraphEnrichmentResponse.model_validate(service.enrich(document_id))


@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    responses={
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Search embedded knowledge chunks",
)
def search_knowledge(
    request: KnowledgeSearchRequest,
    service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> KnowledgeSearchResponse:
    evidence = service.search(
        request.query,
        top_k=request.top_k,
        similarity_threshold=request.similarity_threshold,
        source_type=request.source_type,
        document_id=request.document_id,
    )
    return KnowledgeSearchResponse(
        results=[RetrievedEvidenceResponse.model_validate(item) for item in evidence]
    )
