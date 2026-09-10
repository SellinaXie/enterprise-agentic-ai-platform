"""Schema-constrained extraction and API contracts for the V6 knowledge graph."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge_graph import KnowledgeEntityType, KnowledgeRelationshipType


class ExtractionModel(BaseModel):
    """Closed output contract for untrusted model-generated graph candidates."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExtractedEntity(ExtractionModel):
    """One entity candidate grounded in exactly one source chunk."""

    local_key: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    canonical_name: str = Field(min_length=1, max_length=300)
    entity_type: KnowledgeEntityType
    description: str | None = Field(default=None, max_length=2_000)
    confidence: float = Field(ge=0.0, le=1.0)
    source_chunk_id: UUID


class EntityExtractionResult(ExtractionModel):
    """Bounded entity extraction output for a single chunk."""

    entities: list[ExtractedEntity] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def local_keys_must_be_unique(self) -> "EntityExtractionResult":
        keys = [entity.local_key for entity in self.entities]
        if len(keys) != len(set(keys)):
            raise ValueError("Extracted entity local keys must be unique")
        return self


class ExtractedRelationship(ExtractionModel):
    """One controlled edge referencing only entity keys from the same chunk."""

    source_entity_key: str = Field(min_length=1, max_length=100)
    target_entity_key: str = Field(min_length=1, max_length=100)
    relationship_type: KnowledgeRelationshipType
    description: str | None = Field(default=None, max_length=2_000)
    confidence: float = Field(ge=0.0, le=1.0)
    source_chunk_id: UUID

    @model_validator(mode="after")
    def reject_self_edge(self) -> "ExtractedRelationship":
        if self.source_entity_key == self.target_entity_key:
            raise ValueError("Self-relationships are not allowed")
        return self


class RelationshipExtractionResult(ExtractionModel):
    """Bounded relationship extraction output for a single chunk."""

    relationships: list[ExtractedRelationship] = Field(default_factory=list, max_length=200)


class KnowledgeGraphEnrichmentResponse(BaseModel):
    """Minimal result from enriching an existing V3 document."""

    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    entity_count: int = Field(ge=0)
    relationship_count: int = Field(ge=0)
    status: Literal["completed"]
