"""Typed arguments and provider-neutral results for approved V4 tools."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.knowledge import KnowledgeSourceType, RetrievedEvidence
from app.models.knowledge_graph import (
    GraphNeighborhood,
    GraphRetrievalExecutionMetadata,
    KnowledgeEntityType,
)


class SearchKnowledgeArguments(BaseModel):
    """Strict semantic-search arguments exposed to the model."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=4_000)
    top_k: int = Field(ge=1, le=20)


class GetKnowledgeDocumentArguments(BaseModel):
    """Strict document lookup arguments exposed to the model."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID


class SearchKnowledgeGraphArguments(BaseModel):
    """Strict bounded graph-search arguments exposed only to the Evidence Agent."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=4_000)
    max_depth: int = Field(ge=1, le=5)
    entity_types: list[KnowledgeEntityType] | None = Field(max_length=11)


@dataclass(frozen=True, slots=True)
class ObservedKnowledgeDocument:
    """Bounded document observation supplied back to the agent."""

    document_id: UUID
    title: str
    source_type: KnowledgeSourceType
    content_excerpt: str
    metadata: dict[str, Any]
    truncated: bool


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    """Normalized result from any allowlisted tool implementation."""

    tool_name: str
    success: bool
    summary: str
    evidence: tuple[RetrievedEvidence, ...] = ()
    document: ObservedKnowledgeDocument | None = None
    graph_neighborhood: GraphNeighborhood | None = None
    graph_retrieval: GraphRetrievalExecutionMetadata | None = None
    error_code: str | None = None
    cached: bool = False


@dataclass(frozen=True, slots=True)
class ToolHistoryEntry:
    """Safe per-call state retained inside one graph execution."""

    step: int
    tool_name: str
    success: bool
    summary: str
    argument_keys: tuple[str, ...]
    call_fingerprint: str
    cached: bool
    error_code: str | None = None
    graph_retrieval: GraphRetrievalExecutionMetadata | None = None
