"""Typed, format-neutral contracts for V6.5 document parsing and ingestion."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.knowledge import KnowledgeDocumentRecord, KnowledgeSourceType


class FileFormat(StrEnum):
    """Hard allowlist of V6.5 enterprise file formats."""

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"


class ParsedDocumentSegment(BaseModel):
    """A source block that can contribute page or section provenance to chunks."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    section_heading: str | None = Field(default=None, max_length=500)


class ParsedDocument(BaseModel):
    """Format-neutral parser output consumed by the file ingestion service."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=300)
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=200)
    file_format: FileFormat
    source_type: KnowledgeSourceType
    page_count: int | None = Field(default=None, ge=1)
    sections: list[str] = Field(default_factory=list, max_length=1_000)
    parser_name: str = Field(min_length=1, max_length=100)
    parser_version: str | None = Field(default=None, max_length=100)
    extraction_method: str = Field(min_length=1, max_length=100)
    metadata: dict[str, Any] = Field(default_factory=dict)
    segments: list[ParsedDocumentSegment] = Field(default_factory=list, max_length=10_000)


class GraphEnrichmentStatus(StrEnum):
    """Outcome of optional post-commit graph enrichment."""

    NOT_REQUESTED = "not_requested"
    DISABLED = "disabled"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class FileIngestionResult:
    """Safe result returned after parsing and existing V3 ingestion."""

    document: KnowledgeDocumentRecord
    filename: str
    mime_type: str
    parser: str
    extraction_method: str
    normalized_character_count: int
    chunk_count: int
    duplicate: bool
    graph_enrichment_status: GraphEnrichmentStatus
    graph_error_code: str | None = None

    @property
    def document_id(self) -> UUID:
        return self.document.document_id

    @property
    def created_at(self) -> datetime:
        return self.document.created_at

    @property
    def title(self) -> str:
        return self.document.title

    @property
    def source_type(self) -> KnowledgeSourceType:
        return self.document.source_type
