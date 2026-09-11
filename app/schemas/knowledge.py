"""Typed request and response contracts for the V3 knowledge layer."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.knowledge import KnowledgeSourceType

MAX_METADATA_BYTES = 100_000


class KnowledgeDocumentCreate(BaseModel):
    """Plain-text knowledge ingestion input."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=300)
    source_type: KnowledgeSourceType = KnowledgeSourceType.TEXT
    source_uri: str | None = Field(default=None, max_length=2_000)
    external_id: str | None = Field(default=None, max_length=300)
    content: str = Field(min_length=1, max_length=1_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject unbounded or non-JSON metadata before persistence."""
        try:
            encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must contain JSON-compatible values") from exc
        if len(encoded) > MAX_METADATA_BYTES:
            raise ValueError("metadata exceeds the 100,000-byte limit")
        return value


class KnowledgeDocumentResponse(BaseModel):
    """Stored knowledge document metadata and normalized content."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    title: str
    source_type: KnowledgeSourceType
    source_uri: str | None
    external_id: str | None
    content: str
    metadata: dict[str, Any]
    content_hash: str
    created_at: datetime
    updated_at: datetime


class KnowledgeIngestionResponse(BaseModel):
    """Summary of a completed document ingestion transaction."""

    document: KnowledgeDocumentResponse
    chunk_count: int = Field(ge=1)


class KnowledgeSearchRequest(BaseModel):
    """Minimal semantic search input."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=4_000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    similarity_threshold: float | None = Field(default=None, ge=-1.0, le=1.0)
    source_type: KnowledgeSourceType | None = None
    document_id: UUID | None = None


class RetrievedEvidenceResponse(BaseModel):
    """Ranked knowledge chunk with source attribution."""

    model_config = ConfigDict(from_attributes=True)

    chunk_id: UUID
    document_id: UUID
    document_title: str
    content: str
    similarity_score: float | None
    source_type: KnowledgeSourceType
    metadata: dict[str, Any]


class KnowledgeSearchResponse(BaseModel):
    """Ordered semantic-search results."""

    results: list[RetrievedEvidenceResponse]
