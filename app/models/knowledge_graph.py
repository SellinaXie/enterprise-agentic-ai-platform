"""Persistence-neutral domain models for the V6 relational knowledge graph."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.knowledge import RetrievedEvidence


class KnowledgeEntityType(StrEnum):
    """Small controlled entity taxonomy for enterprise knowledge."""

    ORGANIZATION = "organization"
    PROCESS = "process"
    SYSTEM = "system"
    POLICY = "policy"
    REGULATION = "regulation"
    RISK = "risk"
    DATA_ASSET = "data_asset"
    AI_CAPABILITY = "ai_capability"
    CONTROL = "control"
    ROLE = "role"
    OTHER = "other"


class KnowledgeRelationshipType(StrEnum):
    """Controlled relationship vocabulary accepted from extraction."""

    USES = "uses"
    DEPENDS_ON = "depends_on"
    PART_OF = "part_of"
    GOVERNED_BY = "governed_by"
    AFFECTED_BY = "affected_by"
    CREATES_RISK = "creates_risk"
    MITIGATED_BY = "mitigated_by"
    REQUIRES = "requires"
    PRODUCES = "produces"
    CONSUMES = "consumes"
    RELATED_TO = "related_to"


@dataclass(frozen=True, slots=True)
class KnowledgeEntityRecord:
    """Resolved graph entity persisted independently of source mentions."""

    entity_id: UUID
    entity_type: KnowledgeEntityType
    canonical_name: str
    normalized_name: str
    description: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeEntityMentionRecord:
    """Provenance link from an entity to a V3 document chunk."""

    mention_id: UUID
    entity_id: UUID
    document_id: UUID
    chunk_id: UUID
    mention_text: str
    confidence: float
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class KnowledgeRelationshipRecord:
    """Directed, typed, source-grounded graph edge."""

    relationship_id: UUID
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: KnowledgeRelationshipType
    description: str | None
    confidence: float
    source_chunk_id: UUID
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class GraphTraversalData:
    """Repository result before mapping persistence records to public graph models."""

    matched_entities: tuple[KnowledgeEntityRecord, ...]
    related_entities: tuple[KnowledgeEntityRecord, ...]
    relationships: tuple[KnowledgeRelationshipRecord, ...]
    mentions: tuple[KnowledgeEntityMentionRecord, ...]
    evidence: tuple[RetrievedEvidence, ...]
    depth_used: int


@dataclass(frozen=True, slots=True)
class KnowledgeGraphEnrichmentResult:
    """Summary of deterministic graph enrichment for one existing document."""

    document_id: UUID
    entity_count: int
    relationship_count: int
    status: Literal["completed"] = "completed"


class GraphModel(BaseModel):
    """Closed base model for graph retrieval and execution metadata."""

    model_config = ConfigDict(extra="forbid")


class GraphEntityResult(GraphModel):
    """Typed entity exposed by graph retrieval rather than an ORM object."""

    entity_id: UUID
    entity_type: KnowledgeEntityType
    canonical_name: str
    normalized_name: str
    description: str | None = None


class GraphRelationshipResult(GraphModel):
    """Typed relationship with entity labels and complete source provenance."""

    relationship_id: UUID
    source_entity_id: UUID
    source_entity_name: str
    target_entity_id: UUID
    target_entity_name: str
    relationship_type: KnowledgeRelationshipType
    description: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_document_id: UUID
    source_chunk_id: UUID


class GraphNeighborhood(GraphModel):
    """Bounded relationship-aware result plus graph-derived source chunks."""

    query: str = Field(min_length=1, max_length=4_000)
    matched_entities: list[GraphEntityResult]
    related_entities: list[GraphEntityResult]
    relationships: list[GraphRelationshipResult]
    source_document_ids: list[UUID]
    source_chunk_ids: list[UUID]
    depth_used: int = Field(ge=0, le=5)
    evidence: list[RetrievedEvidence]

    @classmethod
    def empty(cls, query: str) -> "GraphNeighborhood":
        return cls(
            query=query,
            matched_entities=[],
            related_entities=[],
            relationships=[],
            source_document_ids=[],
            source_chunk_ids=[],
            depth_used=0,
            evidence=[],
        )


class GraphRetrievalExecutionMetadata(GraphModel):
    """Safe aggregate graph/hybrid retrieval facts for execution JSONB."""

    graph_retrieval_used: bool = False
    matched_entity_count: int = Field(default=0, ge=0)
    relationship_count: int = Field(default=0, ge=0)
    graph_depth_used: int = Field(default=0, ge=0, le=5)
    vector_evidence_count: int = Field(default=0, ge=0)
    graph_evidence_count: int = Field(default=0, ge=0)
    hybrid_evidence_count: int = Field(default=0, ge=0)
    degraded_graph_mode: bool = False
    graph_error_code: str | None = Field(default=None, max_length=100)
    vector_error_code: str | None = Field(default=None, max_length=100)


@dataclass(frozen=True, slots=True)
class HybridRetrievalResult:
    """Merged chunks, relationship neighborhood, and safe retrieval diagnostics."""

    evidence: tuple[RetrievedEvidence, ...]
    neighborhood: GraphNeighborhood
    metadata: GraphRetrievalExecutionMetadata


@dataclass(frozen=True, slots=True)
class HybridRAGPreparation:
    """Assessment-facing hybrid context with the same core V3 preparation fields."""

    query: str
    evidence: tuple[RetrievedEvidence, ...]
    context: str
    graph_retrieval: GraphRetrievalExecutionMetadata
