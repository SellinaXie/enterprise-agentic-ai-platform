"""Reusable V7A retrieval evaluation runner and lightweight argparse CLI."""

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.evaluation.dataset import DEFAULT_DATASET_PATH, load_evaluation_dataset
from app.evaluation.fixtures import DeterministicGraphRetrieval, DeterministicVectorRetrieval
from app.evaluation.metrics import (
    aggregate_case_results,
    calculate_graph_metrics,
    calculate_retrieval_metrics,
    evidence_origin_mix,
)
from app.evaluation.models import (
    CaseEvaluationResult,
    EvaluationCase,
    EvaluationConfiguration,
    EvaluationDataset,
    EvaluationMode,
    EvaluationQueryType,
    EvaluationReport,
    EvidenceObservation,
    GraphMetrics,
    RelationshipObservation,
    RetrievalMetrics,
)
from app.evaluation.reports import (
    build_comparison,
    format_comparison,
    format_report_summary,
    write_comparison,
    write_evaluation_report,
)
from app.knowledge_graph.hybrid import HybridRetrievalService
from app.models.knowledge import RetrievedEvidence
from app.models.knowledge_graph import GraphNeighborhood, HybridRetrievalResult


class VectorRetrievalProtocol(Protocol):
    """Existing vector retrieval shape consumed directly by evaluation."""

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        **kwargs: object,
    ) -> list[RetrievedEvidence]: ...


class GraphRetrievalProtocol(Protocol):
    """Existing graph retrieval shape consumed directly by evaluation."""

    def search(
        self,
        query: str,
        *,
        max_depth: int | None = None,
        **kwargs: object,
    ) -> GraphNeighborhood: ...


class HybridRetrievalProtocol(Protocol):
    """Existing hybrid result shape consumed directly by evaluation."""

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        max_depth: int | None = None,
    ) -> HybridRetrievalResult: ...


class EvaluationRunner:
    """Execute one benchmark across injected vector, graph, and hybrid services."""

    def __init__(
        self,
        *,
        dataset: EvaluationDataset,
        vector: VectorRetrievalProtocol,
        graph: GraphRetrievalProtocol,
        hybrid: HybridRetrievalProtocol,
        configuration: EvaluationConfiguration,
        execution_profile: str,
    ) -> None:
        self._dataset = dataset
        self._vector = vector
        self._graph = graph
        self._hybrid = hybrid
        self._configuration = configuration
        self._execution_profile = execution_profile

    def run(self, mode: EvaluationMode) -> EvaluationReport:
        """Run compatible cases and return actual calculated metrics."""
        results = [self._run_case(case, mode) for case in self._dataset.cases]
        skipped = [item.query_id for item in results if item.skipped]
        return EvaluationReport(
            generated_at=datetime.now(UTC),
            execution_profile=self._execution_profile,
            evaluation_mode=mode,
            dataset_id=self._dataset.dataset_id,
            dataset_version=self._dataset.version,
            synthetic=self._dataset.synthetic,
            total_cases=len(results),
            evaluated_cases=len(results) - len(skipped),
            skipped_cases=skipped,
            configuration=self._configuration,
            cases=results,
            aggregate_metrics=aggregate_case_results(results),
            warnings=[
                "Synthetic deterministic fixture results; not live retrieval-quality metrics.",
                "Live OpenAI/PostgreSQL evaluation was not requested and was skipped.",
            ],
        )

    def _run_case(self, case: EvaluationCase, mode: EvaluationMode) -> CaseEvaluationResult:
        if mode not in case.modes:
            return CaseEvaluationResult(
                query_id=case.query_id,
                query_type=case.query_type,
                skipped=True,
                skip_reason=f"{mode.value} mode is not applicable to this benchmark case",
                retrieval_metrics=RetrievalMetrics(),
                graph_metrics=GraphMetrics(),
            )

        neighborhood = None
        if mode == EvaluationMode.VECTOR:
            evidence = self._vector.search(case.query, top_k=self._configuration.top_k)
        elif mode == EvaluationMode.GRAPH:
            neighborhood = self._graph.search(
                case.query,
                max_depth=self._configuration.graph_max_depth,
            )
            evidence = neighborhood.evidence
        else:
            result = self._hybrid.search(
                case.query,
                top_k=self._configuration.top_k,
                max_depth=self._configuration.graph_max_depth,
            )
            evidence = list(result.evidence)
            neighborhood = result.neighborhood

        negative = case.query_type == EvaluationQueryType.NEGATIVE_NO_ANSWER
        retrieval_metrics = calculate_retrieval_metrics(
            evidence,
            case.expected,
            k=self._configuration.top_k,
            negative=negative,
        )
        graph_metrics = calculate_graph_metrics(
            neighborhood,
            evidence,
            case.expected,
            self._dataset.documents,
            self._dataset.relationships,
        )
        return CaseEvaluationResult(
            query_id=case.query_id,
            query_type=case.query_type,
            retrieved_evidence=[_observation(item) for item in evidence],
            retrieved_entities=(
                []
                if neighborhood is None
                else [
                    item.canonical_name
                    for item in (*neighborhood.matched_entities, *neighborhood.related_entities)
                ]
            ),
            retrieved_relationships=(
                []
                if neighborhood is None
                else [
                    RelationshipObservation(
                        source_entity=item.source_entity_name,
                        relationship_type=item.relationship_type,
                        target_entity=item.target_entity_name,
                        source_document_id=item.source_document_id,
                        source_chunk_id=item.source_chunk_id,
                    )
                    for item in neighborhood.relationships
                ]
            ),
            retrieval_metrics=retrieval_metrics,
            graph_metrics=graph_metrics,
            evidence_origin_mix=evidence_origin_mix(evidence),
        )


def build_deterministic_runner(
    dataset: EvaluationDataset,
    settings: Settings,
) -> EvaluationRunner:
    """Wire dataset fixtures through the existing V6 hybrid merge service."""
    vector = DeterministicVectorRetrieval(dataset)
    graph = DeterministicGraphRetrieval(dataset)
    hybrid = HybridRetrievalService(vector=vector, graph=graph)  # type: ignore[arg-type]
    return EvaluationRunner(
        dataset=dataset,
        vector=vector,
        graph=graph,
        hybrid=hybrid,
        configuration=configuration_from_settings(settings),
        execution_profile="deterministic_fixture",
    )


def configuration_from_settings(settings: Settings) -> EvaluationConfiguration:
    """Copy only non-secret settings relevant to retrieval comparability."""
    return EvaluationConfiguration(
        embedding_model=settings.openai_embedding_model,
        embedding_dimensions=settings.openai_embedding_dimension,
        top_k=settings.rag_retrieval_top_k,
        similarity_threshold=settings.rag_similarity_threshold,
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        graph_max_depth=settings.graph_max_depth,
        graph_min_confidence=settings.graph_min_confidence,
        graph_max_entities=settings.graph_max_entities,
    )


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run deterministic evaluation modes and write JSON reports."""
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--mode", choices=[item.value for item in EvaluationMode])
    selection.add_argument("--all", action="store_true", help="run vector, graph, and hybrid")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/evaluation"))
    arguments = parser.parse_args(argv)

    dataset = load_evaluation_dataset(arguments.dataset)
    runner = build_deterministic_runner(dataset, Settings())
    modes = list(EvaluationMode) if arguments.all else [EvaluationMode(arguments.mode)]
    reports = []
    for mode in modes:
        report = runner.run(mode)
        destination = write_evaluation_report(report, arguments.output_dir)
        reports.append(report)
        print(format_report_summary(report))
        print(f"Report: {destination}")
    if len(reports) > 1:
        comparison = build_comparison(reports)
        destination = write_comparison(comparison, arguments.output_dir)
        print(format_comparison(comparison))
        print(f"Comparison: {destination}")
    return 0


def _observation(item: RetrievedEvidence) -> EvidenceObservation:
    return EvidenceObservation(
        document_id=item.document_id,
        chunk_id=item.chunk_id,
        title=item.document_title,
        retrieval_origin=item.retrieval_source,
    )


if __name__ == "__main__":
    raise SystemExit(run_cli())
