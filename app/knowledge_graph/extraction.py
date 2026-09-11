"""Schema-constrained OpenAI entity and relationship extraction services."""

from typing import Protocol
from uuid import UUID

from app.agents.structured_output import StructuredOutput
from app.core.exceptions import InvalidLLMResponseError
from app.knowledge_graph.normalization import canonicalize_entity_name, normalize_entity_name
from app.knowledge_graph.prompts import (
    ENTITY_EXTRACTION_SYSTEM,
    RELATIONSHIP_EXTRACTION_SYSTEM,
    build_entity_extraction_input,
    build_relationship_extraction_input,
)
from app.schemas.knowledge_graph import (
    EntityExtractionResult,
    ExtractedEntity,
    ExtractedRelationship,
    RelationshipExtractionResult,
)


class EntityExtractor(Protocol):
    """Provider-neutral per-chunk entity extraction boundary."""

    def extract(self, *, chunk_id: UUID, content: str) -> EntityExtractionResult: ...


class RelationshipExtractor(Protocol):
    """Provider-neutral per-chunk relationship extraction boundary."""

    def extract(
        self,
        *,
        chunk_id: UUID,
        content: str,
        entities: list[ExtractedEntity],
    ) -> RelationshipExtractionResult: ...


class OpenAIEntityExtractor:
    """Extract, normalize, filter, and deduplicate typed entity candidates."""

    def __init__(
        self,
        structured_output: StructuredOutput,
        *,
        max_entities: int,
        min_confidence: float,
    ) -> None:
        self._structured_output = structured_output
        self._max_entities = max_entities
        self._min_confidence = min_confidence

    def extract(self, *, chunk_id: UUID, content: str) -> EntityExtractionResult:
        result = self._structured_output.generate(
            system=ENTITY_EXTRACTION_SYSTEM,
            user=build_entity_extraction_input(chunk_id=chunk_id, content=content),
            output_model=EntityExtractionResult,
        )
        by_identity: dict[tuple[str, str], ExtractedEntity] = {}
        order: list[tuple[str, str]] = []
        for entity in result.entities:
            if entity.source_chunk_id != chunk_id:
                raise InvalidLLMResponseError
            canonical = canonicalize_entity_name(entity.canonical_name)
            normalized = normalize_entity_name(canonical)
            if not normalized:
                raise InvalidLLMResponseError
            if entity.confidence < self._min_confidence:
                continue
            identity = (entity.entity_type.value, normalized)
            normalized_entity = entity.model_copy(update={"canonical_name": canonical})
            existing = by_identity.get(identity)
            if existing is None:
                order.append(identity)
                by_identity[identity] = normalized_entity
            elif normalized_entity.confidence > existing.confidence:
                by_identity[identity] = normalized_entity
        return EntityExtractionResult(
            entities=[by_identity[key] for key in order[: self._max_entities]]
        )


class OpenAIRelationshipExtractor:
    """Reject ungrounded entity references and deduplicate controlled edges."""

    def __init__(
        self,
        structured_output: StructuredOutput,
        *,
        min_confidence: float,
    ) -> None:
        self._structured_output = structured_output
        self._min_confidence = min_confidence

    def extract(
        self,
        *,
        chunk_id: UUID,
        content: str,
        entities: list[ExtractedEntity],
    ) -> RelationshipExtractionResult:
        if not entities:
            return RelationshipExtractionResult()
        result = self._structured_output.generate(
            system=RELATIONSHIP_EXTRACTION_SYSTEM,
            user=build_relationship_extraction_input(
                chunk_id=chunk_id,
                content=content,
                entities=entities,
            ),
            output_model=RelationshipExtractionResult,
        )
        allowed_keys = {entity.local_key for entity in entities}
        unique: dict[tuple[str, str, str], ExtractedRelationship] = {}
        order: list[tuple[str, str, str]] = []
        for relationship in result.relationships:
            if relationship.source_chunk_id != chunk_id:
                raise InvalidLLMResponseError
            if (
                relationship.source_entity_key not in allowed_keys
                or relationship.target_entity_key not in allowed_keys
            ):
                raise InvalidLLMResponseError
            if relationship.confidence < self._min_confidence:
                continue
            identity = (
                relationship.source_entity_key,
                relationship.target_entity_key,
                relationship.relationship_type.value,
            )
            existing = unique.get(identity)
            if existing is None:
                order.append(identity)
                unique[identity] = relationship
            elif relationship.confidence > existing.confidence:
                unique[identity] = relationship
        return RelationshipExtractionResult(relationships=[unique[key] for key in order])
