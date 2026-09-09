"""Persistence-neutral knowledge and retrieval domain models."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class KnowledgeSourceType(StrEnum):
    """Small V3 vocabulary for knowledge source provenance."""

    TEXT = "text"
    MARKDOWN = "markdown"
    POLICY = "policy"
    REPORT = "report"
    CASE_STUDY = "case_study"
    MANUAL = "manual"
    SYNTHETIC = "synthetic"


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRecord:
    """Persistence-neutral normalized knowledge document."""

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


@dataclass(frozen=True, slots=True)
class KnowledgeChunkRecord:
    """Persistence-neutral embedded knowledge chunk."""

    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    embedding: list[float]
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    """Chunk content paired with a validated embedding before persistence."""

    chunk_index: int
    content: str
    embedding: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    """Ranked source evidence returned by vector retrieval."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    content: str
    similarity_score: float
    source_type: KnowledgeSourceType
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class RAGPreparation:
    """Evidence and controlled context prepared for one assessment."""

    query: str
    evidence: tuple[RetrievedEvidence, ...]
    context: str


@dataclass(frozen=True, slots=True)
class KnowledgeIngestionResult:
    """Domain result for one atomic ingestion operation."""

    document: KnowledgeDocumentRecord
    chunk_count: int
