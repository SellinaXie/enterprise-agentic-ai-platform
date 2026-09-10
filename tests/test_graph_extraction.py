"""Schema and service tests for source-grounded graph extraction."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import InvalidLLMResponseError
from app.knowledge_graph.extraction import OpenAIEntityExtractor, OpenAIRelationshipExtractor
from app.models.knowledge_graph import KnowledgeEntityType, KnowledgeRelationshipType
from app.schemas.knowledge_graph import (
    EntityExtractionResult,
    ExtractedEntity,
    ExtractedRelationship,
    RelationshipExtractionResult,
)


class StubStructuredOutput:
    """Return queued schema instances without a provider call."""

    def __init__(self, *outputs: object) -> None:
        self.outputs = list(outputs)

    def generate(self, **_: object) -> object:
        return self.outputs.pop(0)


def _entity(chunk_id: object, **updates: object) -> ExtractedEntity:
    values = {
        "local_key": "loan_system",
        "canonical_name": " Loan   System ",
        "entity_type": KnowledgeEntityType.SYSTEM,
        "description": "Synthetic system",
        "confidence": 0.9,
        "source_chunk_id": chunk_id,
    }
    values.update(updates)
    return ExtractedEntity.model_validate(values)


def test_entity_schema_rejects_unknown_taxonomy_and_duplicate_keys() -> None:
    chunk_id = uuid4()
    with pytest.raises(ValidationError):
        _entity(chunk_id, entity_type="database")
    with pytest.raises(ValidationError):
        EntityExtractionResult(entities=[_entity(chunk_id), _entity(chunk_id)])


def test_entity_extractor_normalizes_filters_and_deduplicates() -> None:
    chunk_id = uuid4()
    output = EntityExtractionResult(
        entities=[
            _entity(chunk_id, confidence=0.8),
            _entity(
                chunk_id,
                local_key="duplicate",
                canonical_name="loan system",
                confidence=0.95,
            ),
            _entity(chunk_id, local_key="weak", canonical_name="Weak", confidence=0.2),
        ]
    )
    extractor = OpenAIEntityExtractor(
        StubStructuredOutput(output),  # type: ignore[arg-type]
        max_entities=20,
        min_confidence=0.5,
    )

    result = extractor.extract(chunk_id=chunk_id, content="Loan System is used.")

    assert len(result.entities) == 1
    assert result.entities[0].canonical_name == "loan system"
    assert result.entities[0].confidence == 0.95


def test_entity_extractor_rejects_wrong_source_chunk() -> None:
    chunk_id = uuid4()
    extractor = OpenAIEntityExtractor(
        StubStructuredOutput(EntityExtractionResult(entities=[_entity(uuid4())])),  # type: ignore[arg-type]
        max_entities=20,
        min_confidence=0.5,
    )

    with pytest.raises(InvalidLLMResponseError):
        extractor.extract(chunk_id=chunk_id, content="Synthetic source")


def test_relationship_schema_rejects_unknown_type_and_self_edge() -> None:
    chunk_id = uuid4()
    values = {
        "source_entity_key": "a",
        "target_entity_key": "a",
        "relationship_type": KnowledgeRelationshipType.USES,
        "confidence": 0.8,
        "source_chunk_id": chunk_id,
    }
    with pytest.raises(ValidationError):
        ExtractedRelationship.model_validate(values)
    values.update(target_entity_key="b", relationship_type="owns")
    with pytest.raises(ValidationError):
        ExtractedRelationship.model_validate(values)


def test_relationship_extractor_rejects_unobserved_entity_reference() -> None:
    chunk_id = uuid4()
    entities = [_entity(chunk_id)]
    relationship = ExtractedRelationship(
        source_entity_key="loan_system",
        target_entity_key="invented",
        relationship_type=KnowledgeRelationshipType.DEPENDS_ON,
        confidence=0.9,
        source_chunk_id=chunk_id,
    )
    extractor = OpenAIRelationshipExtractor(
        StubStructuredOutput(RelationshipExtractionResult(relationships=[relationship])),  # type: ignore[arg-type]
        min_confidence=0.5,
    )

    with pytest.raises(InvalidLLMResponseError):
        extractor.extract(chunk_id=chunk_id, content="Synthetic source", entities=entities)
