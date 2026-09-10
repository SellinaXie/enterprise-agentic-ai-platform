"""V7A mode execution, aggregation, serialization, comparison, and reproducibility tests."""

import json
from pathlib import Path

import pytest

from app.core.config import Settings
from app.evaluation.dataset import load_evaluation_dataset
from app.evaluation.models import EvaluationMode, EvaluationReport
from app.evaluation.reports import build_comparison, format_comparison
from app.evaluation.runner import build_deterministic_runner, run_cli
from app.models.knowledge import RetrievalSource


@pytest.fixture
def reports() -> dict[EvaluationMode, EvaluationReport]:
    dataset = load_evaluation_dataset()
    runner = build_deterministic_runner(dataset, Settings(_env_file=None))
    return {mode: runner.run(mode) for mode in EvaluationMode}


def test_vector_graph_and_hybrid_modes_calculate_expected_aggregate_metrics(
    reports: dict[EvaluationMode, EvaluationReport],
) -> None:
    vector = reports[EvaluationMode.VECTOR]
    graph = reports[EvaluationMode.GRAPH]
    hybrid = reports[EvaluationMode.HYBRID]

    assert vector.aggregate_metrics.retrieval.hit_rate_at_k == 0.875
    assert vector.aggregate_metrics.retrieval.recall_at_k == 0.75
    assert vector.aggregate_metrics.graph.relationship_hit_rate is None
    assert graph.aggregate_metrics.retrieval.hit_rate_at_k == 1.0
    assert graph.aggregate_metrics.retrieval.false_positive_rate == 0.0
    assert hybrid.aggregate_metrics.retrieval.hit_rate_at_k == 1.0
    assert hybrid.aggregate_metrics.retrieval.recall_at_k == 1.0
    assert hybrid.aggregate_metrics.graph.relationship_hit_rate == 1.0


def test_runner_skips_only_incompatible_graph_case(
    reports: dict[EvaluationMode, EvaluationReport],
) -> None:
    graph = reports[EvaluationMode.GRAPH]

    assert graph.evaluated_cases == 8
    assert graph.skipped_cases == ["q09_architecture_components"]
    skipped = next(item for item in graph.cases if item.skipped)
    assert skipped.skip_reason is not None


def test_hybrid_report_preserves_document_chunk_relationship_and_origin_provenance(
    reports: dict[EvaluationMode, EvaluationReport],
) -> None:
    hybrid = reports[EvaluationMode.HYBRID]
    case = next(item for item in hybrid.cases if item.query_id == "q01_human_approval")

    assert case.retrieved_evidence[0].document_id
    assert case.retrieved_evidence[0].chunk_id
    assert case.evidence_origin_mix[RetrievalSource.BOTH] == 2
    assert case.retrieved_relationships[0].source_document_id
    assert case.retrieved_relationships[0].source_chunk_id
    assert case.graph_metrics.provenance_coverage == 1.0


def test_configuration_snapshot_contains_retrieval_settings_and_no_secrets(
    reports: dict[EvaluationMode, EvaluationReport],
) -> None:
    report = reports[EvaluationMode.HYBRID]
    serialized = report.model_dump_json()

    assert report.configuration.embedding_model == "text-embedding-3-small"
    assert report.configuration.embedding_dimensions == 1536
    assert report.configuration.top_k == 5
    assert report.configuration.graph_max_depth == 2
    assert "api_key" not in serialized
    assert 'embedding"' not in serialized


def test_deterministic_runs_reproduce_cases_and_metrics() -> None:
    dataset = load_evaluation_dataset()
    runner = build_deterministic_runner(dataset, Settings(_env_file=None))

    first = runner.run(EvaluationMode.HYBRID)
    second = runner.run(EvaluationMode.HYBRID)

    assert first.aggregate_metrics == second.aggregate_metrics
    assert first.cases == second.cases
    assert first.generated_at <= second.generated_at


def test_graph_depth_configuration_changes_bounded_fixture_results() -> None:
    dataset = load_evaluation_dataset()
    shallow = build_deterministic_runner(
        dataset,
        Settings(_env_file=None, GRAPH_MAX_DEPTH=1),
    ).run(EvaluationMode.GRAPH)
    multi_hop = next(
        item for item in shallow.cases if item.query_id == "q03_system_process_policy_path"
    )

    assert multi_hop.retrieved_evidence == []
    assert multi_hop.retrieval_metrics.hit_rate_at_k == 0.0
    assert multi_hop.graph_metrics.path_success == 0.0


def test_comparison_aligns_actual_metrics_and_uses_null_for_unsupported(
    reports: dict[EvaluationMode, EvaluationReport],
) -> None:
    comparison = build_comparison(list(reports.values()))
    rows = {item.metric: item.values for item in comparison.rows}

    assert rows["relationship_hit_rate"][EvaluationMode.VECTOR] is None
    assert rows["relationship_hit_rate"][EvaluationMode.GRAPH] == 1.0
    assert rows["recall_at_k"][EvaluationMode.HYBRID] > rows["recall_at_k"][EvaluationMode.VECTOR]
    rendered = format_comparison(comparison)
    assert "N/A" in rendered
    assert "Hybrid" in rendered


def test_cli_writes_machine_readable_reports_and_comparison(tmp_path: Path) -> None:
    exit_code = run_cli(["--all", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    report_paths = [tmp_path / f"v7a_{mode.value}.json" for mode in EvaluationMode]
    assert all(path.exists() for path in report_paths)
    comparison = json.loads((tmp_path / "v7a_comparison.json").read_text(encoding="utf-8"))
    assert comparison["synthetic"] is True
    assert {row["metric"] for row in comparison["rows"]} >= {
        "hit_rate_at_k",
        "relationship_hit_rate",
        "false_positive_rate",
    }
