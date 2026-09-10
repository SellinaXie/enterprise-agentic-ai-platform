"""Machine-readable report persistence and calculated mode comparisons."""

from datetime import UTC, datetime
from pathlib import Path

from app.evaluation.models import (
    ComparisonMetricRow,
    EvaluationComparison,
    EvaluationMode,
    EvaluationReport,
)


def write_evaluation_report(report: EvaluationReport, output_dir: Path) -> Path:
    """Write one non-secret JSON report below the caller-selected output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"v7a_{report.evaluation_mode.value}.json"
    destination.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return destination


def build_comparison(reports: list[EvaluationReport]) -> EvaluationComparison:
    """Align actual calculated metrics and retain null for unsupported values."""
    if not reports:
        raise ValueError("at least one evaluation report is required")
    dataset_keys = {(item.dataset_id, item.dataset_version) for item in reports}
    if len(dataset_keys) != 1:
        raise ValueError("comparison reports must use the same dataset version")
    by_mode = {item.evaluation_mode: item for item in reports}
    if len(by_mode) != len(reports):
        raise ValueError("comparison reports must use unique evaluation modes")
    metrics = {
        "hit_rate_at_k": lambda report: report.aggregate_metrics.retrieval.hit_rate_at_k,
        "precision_at_k": lambda report: report.aggregate_metrics.retrieval.precision_at_k,
        "recall_at_k": lambda report: report.aggregate_metrics.retrieval.recall_at_k,
        "mrr": lambda report: report.aggregate_metrics.retrieval.mrr,
        "entity_hit_rate": lambda report: report.aggregate_metrics.graph.entity_hit_rate,
        "relationship_hit_rate": lambda report: (
            report.aggregate_metrics.graph.relationship_hit_rate
        ),
        "path_success": lambda report: report.aggregate_metrics.graph.path_success,
        "provenance_coverage": lambda report: report.aggregate_metrics.graph.provenance_coverage,
        "false_positive_rate": lambda report: (
            report.aggregate_metrics.retrieval.false_positive_rate
        ),
    }
    modes = [mode for mode in EvaluationMode if mode in by_mode]
    rows = [
        ComparisonMetricRow(
            metric=name,
            values={mode: accessor(by_mode[mode]) for mode in modes},
        )
        for name, accessor in metrics.items()
    ]
    first = reports[0]
    return EvaluationComparison(
        generated_at=datetime.now(UTC),
        dataset_id=first.dataset_id,
        dataset_version=first.dataset_version,
        synthetic=all(item.synthetic for item in reports),
        modes=modes,
        rows=rows,
        warnings=["Calculated synthetic fixture comparison; not a live retrieval-quality claim."],
    )


def write_comparison(comparison: EvaluationComparison, output_dir: Path) -> Path:
    """Write the aligned comparison as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "v7a_comparison.json"
    destination.write_text(comparison.model_dump_json(indent=2), encoding="utf-8")
    return destination


def format_report_summary(report: EvaluationReport) -> str:
    """Return a concise human-readable summary with no inferred metrics."""
    retrieval = report.aggregate_metrics.retrieval
    graph = report.aggregate_metrics.graph
    lines = [
        f"Mode: {report.evaluation_mode.value}",
        f"Profile: {report.execution_profile}",
        f"Cases: {report.evaluated_cases}/{report.total_cases}",
        f"Hit Rate@{report.configuration.top_k}: {_display(retrieval.hit_rate_at_k)}",
        f"Precision@{report.configuration.top_k}: {_display(retrieval.precision_at_k)}",
        f"Recall@{report.configuration.top_k}: {_display(retrieval.recall_at_k)}",
        f"MRR: {_display(retrieval.mrr)}",
        f"Entity Hit Rate: {_display(graph.entity_hit_rate)}",
        f"Relationship Hit Rate: {_display(graph.relationship_hit_rate)}",
        f"Path Success: {_display(graph.path_success)}",
        f"Provenance Coverage: {_display(graph.provenance_coverage)}",
        f"Negative-query false positive rate: {_display(retrieval.false_positive_rate)}",
    ]
    return "\n".join(lines)


def format_comparison(comparison: EvaluationComparison) -> str:
    """Render a compact table with N/A for unsupported mode metrics."""
    headings = [mode.value.title() for mode in comparison.modes]
    lines = [f"{'Metric':<28}" + "".join(f"{item:>12}" for item in headings)]
    for row in comparison.rows:
        values = "".join(f"{_display(row.values.get(mode)):>12}" for mode in comparison.modes)
        lines.append(f"{row.metric:<28}{values}")
    return "\n".join(lines)


def _display(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"
