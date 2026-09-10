"""Typed contracts for deterministic V7A retrieval evaluation."""

from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.knowledge import RetrievalSource
from app.models.knowledge_graph import KnowledgeEntityType, KnowledgeRelationshipType


class EvaluationModel(BaseModel):
    """Closed base model for version-controlled benchmark and report data."""

    model_config = ConfigDict(extra="forbid")


class EvaluationMode(StrEnum):
    """Retrieval paths evaluated independently by V7A."""

    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"


class EvaluationQueryType(StrEnum):
    """Reviewable benchmark query categories."""

    SEMANTIC_FACTUAL = "semantic_factual"
    POLICY_LOOKUP = "policy_lookup"
    MULTI_DOCUMENT = "multi_document"
    RELATIONSHIP_IMPACT_CHAIN = "relationship_impact_chain"
    MULTI_HOP_RELATIONSHIP = "multi_hop_relationship"
    NEGATIVE_NO_ANSWER = "negative_no_answer"


class BenchmarkDocument(EvaluationModel):
    """One synthetic source with a stable single-chunk evaluation identity."""

    document_id: UUID
    chunk_id: UUID
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)


class BenchmarkEntity(EvaluationModel):
    """One controlled graph entity available to deterministic graph fixtures."""

    entity_id: UUID
    canonical_name: str = Field(min_length=1, max_length=500)
    entity_type: KnowledgeEntityType


class ExpectedRelationship(EvaluationModel):
    """A name-based relationship expectation independent of generated UUIDs."""

    source_entity: str = Field(min_length=1, max_length=500)
    relationship_type: KnowledgeRelationshipType
    target_entity: str = Field(min_length=1, max_length=500)

    @property
    def key(self) -> tuple[str, KnowledgeRelationshipType, str]:
        return (
            self.source_entity.casefold(),
            self.relationship_type,
            self.target_entity.casefold(),
        )


class BenchmarkRelationship(ExpectedRelationship):
    """One source-grounded graph edge in the synthetic corpus."""

    relationship_id: UUID
    source_document_id: UUID
    source_chunk_id: UUID


class ExpectedGraphPath(EvaluationModel):
    """A bounded path expressed as the exact relationships it must contain."""

    relationships: list[ExpectedRelationship] = Field(min_length=1)


class EvaluationExpectedEvidence(EvaluationModel):
    """Known-relevant evidence and graph facts for one benchmark query."""

    document_ids: list[UUID] = Field(default_factory=list)
    chunk_ids: list[UUID] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relationships: list[ExpectedRelationship] = Field(default_factory=list)
    paths: list[ExpectedGraphPath] = Field(default_factory=list)


class FixtureGraphResult(EvaluationModel):
    """Transparent deterministic graph response used by the network-free profile."""

    matched_entity_ids: list[UUID] = Field(default_factory=list)
    related_entity_ids: list[UUID] = Field(default_factory=list)
    relationship_ids: list[UUID] = Field(default_factory=list)
    evidence_chunk_ids: list[UUID] = Field(default_factory=list)
    depth_used: int = Field(default=0, ge=0, le=5)


class FixtureRetrievalResult(EvaluationModel):
    """Version-controlled fixture outputs, never generated embeddings."""

    vector_chunk_ids: list[UUID] = Field(default_factory=list)
    graph: FixtureGraphResult = Field(default_factory=FixtureGraphResult)


class EvaluationCase(EvaluationModel):
    """One query, its ground truth, and deterministic retrieval fixture."""

    query_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,99}$")
    query: str = Field(min_length=1, max_length=4_000)
    query_type: EvaluationQueryType
    modes: set[EvaluationMode] = Field(min_length=1)
    expected: EvaluationExpectedEvidence
    fixture: FixtureRetrievalResult
    notes: str | None = Field(default=None, max_length=1_000)


class EvaluationDataset(EvaluationModel):
    """Validated synthetic corpus, graph, queries, and known expected evidence."""

    dataset_id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=1_000)
    synthetic: bool
    documents: list[BenchmarkDocument] = Field(min_length=1)
    entities: list[BenchmarkEntity] = Field(default_factory=list)
    relationships: list[BenchmarkRelationship] = Field(default_factory=list)
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_integrity(self) -> Self:
        """Reject ambiguous, invented, or internally inconsistent benchmark references."""
        _require_unique("document IDs", [item.document_id for item in self.documents])
        _require_unique("chunk IDs", [item.chunk_id for item in self.documents])
        _require_unique("entity IDs", [item.entity_id for item in self.entities])
        _require_unique("entity names", [item.canonical_name.casefold() for item in self.entities])
        _require_unique("relationship IDs", [item.relationship_id for item in self.relationships])
        _require_unique("relationship edges", [item.key for item in self.relationships])
        _require_unique("query IDs", [item.query_id for item in self.cases])

        documents = {item.document_id: item for item in self.documents}
        chunks = {item.chunk_id: item for item in self.documents}
        entities = {item.entity_id: item for item in self.entities}
        entity_names = {item.canonical_name.casefold() for item in self.entities}
        relationships = {item.relationship_id: item for item in self.relationships}
        relationship_keys = {item.key for item in self.relationships}

        for relationship in self.relationships:
            if relationship.source_entity.casefold() not in entity_names:
                raise ValueError("relationship source entity is not defined")
            if relationship.target_entity.casefold() not in entity_names:
                raise ValueError("relationship target entity is not defined")
            document = documents.get(relationship.source_document_id)
            chunk = chunks.get(relationship.source_chunk_id)
            if document is None or chunk is None or chunk.document_id != document.document_id:
                raise ValueError("relationship provenance does not identify one corpus source")

        graph_query_types = {
            EvaluationQueryType.RELATIONSHIP_IMPACT_CHAIN,
            EvaluationQueryType.MULTI_HOP_RELATIONSHIP,
        }
        for case in self.cases:
            _require_unique("expected document IDs", case.expected.document_ids)
            _require_unique("expected chunk IDs", case.expected.chunk_ids)
            _require_unique(
                "expected entities", [name.casefold() for name in case.expected.entities]
            )
            _require_unique(
                "expected relationships", [item.key for item in case.expected.relationships]
            )
            if any(item not in documents for item in case.expected.document_ids):
                raise ValueError(f"{case.query_id} has an unknown expected document ID")
            if any(item not in chunks for item in case.expected.chunk_ids):
                raise ValueError(f"{case.query_id} has an unknown expected chunk ID")
            if case.expected.document_ids and case.expected.chunk_ids:
                expected_documents = set(case.expected.document_ids)
                if any(
                    chunks[item].document_id not in expected_documents
                    for item in case.expected.chunk_ids
                ):
                    raise ValueError(
                        f"{case.query_id} expected chunks do not belong to expected documents"
                    )
            if any(name.casefold() not in entity_names for name in case.expected.entities):
                raise ValueError(f"{case.query_id} has an unknown expected entity")
            if any(item.key not in relationship_keys for item in case.expected.relationships):
                raise ValueError(f"{case.query_id} has an unknown expected relationship")
            if case.query_type in graph_query_types and (
                not case.expected.entities or not case.expected.relationships
            ):
                raise ValueError(f"{case.query_id} graph case lacks graph expectations")
            if case.query_type == EvaluationQueryType.NEGATIVE_NO_ANSWER and (
                case.expected.document_ids
                or case.expected.chunk_ids
                or case.expected.entities
                or case.expected.relationships
            ):
                raise ValueError(f"{case.query_id} negative case cannot declare relevant evidence")
            for path in case.expected.paths:
                if any(
                    item.key not in {edge.key for edge in case.expected.relationships}
                    for item in path.relationships
                ):
                    raise ValueError(
                        f"{case.query_id} path is not contained in expected relationships"
                    )
            if any(item not in chunks for item in case.fixture.vector_chunk_ids):
                raise ValueError(f"{case.query_id} fixture has an unknown vector chunk")
            graph = case.fixture.graph
            if any(
                item not in entities
                for item in (*graph.matched_entity_ids, *graph.related_entity_ids)
            ):
                raise ValueError(f"{case.query_id} fixture has an unknown graph entity")
            if any(item not in relationships for item in graph.relationship_ids):
                raise ValueError(f"{case.query_id} fixture has an unknown graph relationship")
            if any(item not in chunks for item in graph.evidence_chunk_ids):
                raise ValueError(f"{case.query_id} fixture has an unknown graph evidence chunk")
            graph_evidence = set(graph.evidence_chunk_ids)
            if any(
                relationships[item].source_chunk_id not in graph_evidence
                for item in graph.relationship_ids
            ):
                raise ValueError(
                    f"{case.query_id} graph relationship lacks its source evidence chunk"
                )
        return self


class RetrievalMetrics(EvaluationModel):
    """Deterministic ranked-retrieval metrics for one case or aggregate."""

    hit_rate_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    precision_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    mrr: float | None = Field(default=None, ge=0.0, le=1.0)
    false_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class GraphMetrics(EvaluationModel):
    """Deterministic expected-graph and source traceability metrics."""

    entity_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    relationship_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    path_success: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance_coverage: float | None = Field(default=None, ge=0.0, le=1.0)


class EvidenceObservation(EvaluationModel):
    """Safe retrieved identity and origin stored in a report."""

    document_id: UUID
    chunk_id: UUID
    title: str
    retrieval_origin: RetrievalSource


class RelationshipObservation(ExpectedRelationship):
    """Retrieved edge identity with its source provenance."""

    source_document_id: UUID
    source_chunk_id: UUID


class CaseEvaluationResult(EvaluationModel):
    """Machine-readable outcome for one benchmark case."""

    query_id: str
    query_type: EvaluationQueryType
    skipped: bool = False
    skip_reason: str | None = None
    retrieved_evidence: list[EvidenceObservation] = Field(default_factory=list)
    retrieved_entities: list[str] = Field(default_factory=list)
    retrieved_relationships: list[RelationshipObservation] = Field(default_factory=list)
    retrieval_metrics: RetrievalMetrics
    graph_metrics: GraphMetrics
    evidence_origin_mix: dict[RetrievalSource, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class EvaluationConfiguration(EvaluationModel):
    """Non-secret retrieval settings needed to compare benchmark runs."""

    embedding_model: str
    embedding_dimensions: int = Field(ge=1)
    top_k: int = Field(ge=1)
    similarity_threshold: float = Field(ge=-1.0, le=1.0)
    chunk_size: int = Field(ge=1)
    chunk_overlap: int = Field(ge=0)
    graph_max_depth: int = Field(ge=1, le=5)
    graph_min_confidence: float = Field(ge=0.0, le=1.0)
    graph_max_entities: int = Field(ge=1)


class AggregateMetrics(EvaluationModel):
    """Macro averages plus aggregate evidence-origin counts."""

    retrieval: RetrievalMetrics
    graph: GraphMetrics
    evidence_origin_mix: dict[RetrievalSource, int] = Field(default_factory=dict)


class EvaluationReport(EvaluationModel):
    """Serializable V7A report for one retrieval mode."""

    generated_at: datetime
    execution_profile: str
    evaluation_mode: EvaluationMode
    dataset_id: str
    dataset_version: str
    synthetic: bool
    total_cases: int = Field(ge=1)
    evaluated_cases: int = Field(ge=0)
    skipped_cases: list[str]
    configuration: EvaluationConfiguration
    cases: list[CaseEvaluationResult]
    aggregate_metrics: AggregateMetrics
    warnings: list[str]


class ComparisonMetricRow(EvaluationModel):
    """One aligned metric with nullable values for unsupported modes."""

    metric: str
    values: dict[EvaluationMode, float | None]


class EvaluationComparison(EvaluationModel):
    """Calculated vector/graph/hybrid comparison with no hardcoded claims."""

    generated_at: datetime
    dataset_id: str
    dataset_version: str
    synthetic: bool
    modes: list[EvaluationMode]
    rows: list[ComparisonMetricRow]
    warnings: list[str]


def _require_unique(label: str, values: list[object]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")
