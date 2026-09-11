"""Plain-text/file knowledge ingestion and semantic-search endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.api.dependencies import (
    get_file_ingestion_service,
    get_graph_enrichment_service,
    get_knowledge_ingestion_service,
    get_retrieval_service,
)
from app.core.exceptions import KnowledgeGraphDisabledError
from app.identity.dependencies import get_authenticated_principal
from app.identity.models import AuthenticatedPrincipal
from app.ingestion.service import FileIngestionService
from app.knowledge_graph.enrichment import KnowledgeGraphEnrichmentService
from app.models.knowledge import KnowledgeSourceType
from app.rag.ingestion import KnowledgeIngestionService
from app.rag.retrieval import RetrievalService
from app.schemas.errors import ErrorResponse
from app.schemas.file_ingestion import FileIngestionResponse
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentResponse,
    KnowledgeIngestionResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    RetrievedEvidenceResponse,
)
from app.schemas.knowledge_graph import KnowledgeGraphEnrichmentResponse

router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(get_authenticated_principal)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)


@router.post(
    "/files",
    response_model=FileIngestionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {"model": ErrorResponse},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Ingest an allowlisted enterprise document",
    description=(
        "Upload a PDF, DOCX, UTF-8 TXT, or Markdown file as multipart form-data. The default "
        "file-content limit is 10 MiB and is configured by MAX_UPLOAD_SIZE_MB. Image-only PDFs "
        "require OCR and are rejected; original file bytes are not retained."
    ),
)
async def ingest_file(
    file: Annotated[
        UploadFile,
        File(description="PDF, DOCX, UTF-8 TXT, or Markdown document"),
    ],
    service: Annotated[FileIngestionService, Depends(get_file_ingestion_service)],
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
    title: Annotated[str | None, Form(max_length=300)] = None,
    source_type: Annotated[KnowledgeSourceType | None, Form()] = None,
    metadata_json: Annotated[
        str | None,
        Form(alias="metadata", description="Optional JSON object with caller metadata"),
    ] = None,
    enrich_graph: Annotated[bool, Form()] = False,
) -> FileIngestionResponse:
    result = await service.ingest_upload(
        file,
        title=title,
        source_type=source_type,
        metadata_json=metadata_json,
        enrich_graph=enrich_graph,
    )
    return FileIngestionResponse.model_validate(result)


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
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
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
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
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
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
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
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
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
