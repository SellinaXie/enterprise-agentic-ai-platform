"""Public multipart ingestion response without binary or filesystem data."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ingestion.models import GraphEnrichmentStatus
from app.models.knowledge import KnowledgeSourceType


class FileIngestionResponse(BaseModel):
    """Typed summary of a completed or deduplicated file ingestion."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    filename: str
    title: str
    source_type: KnowledgeSourceType
    mime_type: str
    parser: str
    extraction_method: str
    normalized_character_count: int = Field(ge=1)
    chunk_count: int = Field(ge=1)
    duplicate: bool
    graph_enrichment_status: GraphEnrichmentStatus
    graph_error_code: str | None = None
    created_at: datetime
