"""V7B report persistence, comparison, and concise human-readable output."""

from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

from app.evaluation.assessment.models import (
    AssessmentCaseEvaluationResult,
    AssessmentComparisonRow,
    AssessmentEvaluationMode,
    AssessmentEvaluationReport,
    AssessmentModeComparison,
    AssessmentScenarioCategory,
)

METRIC_NAMES = (
    "risk_recall",
    "risk_precision",
    "severity_consistency",
    "control_coverage",
    "governance_coverage",
    "human_oversight_accuracy",
    "architecture_fit_score",
    "over_engineering_avoidance",
    "groundedness",
    "unsupported_claim_rate",
    "appropriate_abstention_rate",
    "specialist_preservation",
    "synthesis_transparency",
)


def write_assessment_report(report: AssessmentEvaluationReport, output_dir: Path) -> Path:
    """Persist one V7B report without source text, prompts, credentials, or CoT."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"v7b_{report.mode.value}.json"
    destination.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return destination


def build_assessment_comparison(
    reports: list[AssessmentEvaluationReport],
) -> AssessmentModeComparison:
    """Align actual calculations and derive a Pareto comparison without a magic score."""
    if not reports:
        raise ValueError("at least one V7B report is required")
    dataset_keys = {(item.dataset_id, item.dataset_version) for item in reports}
    if len(dataset_keys) != 1:
        raise ValueError("comparison reports must use the same V7B dataset")
    by_mode = {item.mode: item for item in reports}
    if len(by_mode) != len(reports):
        raise ValueError("comparison reports must use unique execution modes")
    case_sets = [{item.case_id for item in report.cases} for report in reports]
    if any(items != case_sets[0] for items in case_sets[1:]):
        raise ValueError("comparison reports must contain the same benchmark cases")
    modes = [item for item in AssessmentEvaluationMode if item in by_mode]
    rows = [
        AssessmentComparisonRow(
            metric=name,
            values={mode: getattr(by_mode[mode].aggregate_metrics, name) for mode in modes},
        )
        for name in METRIC_NAMES
    ]
    best_by_case = {
        case_id: _pareto_modes([_case_by_id(by_mode[mode], case_id) for mode in modes])
        for case_id in sorted(case_sets[0])
    }
    first = reports[0]
    return AssessmentModeComparison(
        generated_at=datetime.now(UTC),
        dataset_id=first.dataset_id,
        dataset_version=first.dataset_version,
        synthetic=all(item.synthetic for item in reports),
        modes=modes,
        rows=rows,
        key_tradeoffs=_derive_tradeoffs(by_mode, best_by_case),
        best_mode_by_case=best_by_case,
        benchmark_scope={
            "case_count": len(case_sets[0]),
            "synthetic": True,
            "regulated_enterprise_emphasis": True,
            "selection_method": "Pareto frontier over supported per-case deterministic metrics",
            "production_assurance": False,
        },
        warnings=[
            "Synthetic benchmark findings are local to these declared fixtures.",
            "Pareto-optimal modes may tie; no global winner or hidden composite score is used.",
        ],
    )


def write_assessment_comparison(
    comparison: AssessmentModeComparison,
    output_dir: Path,
) -> Path:
    """Write the portfolio-ready V7B comparison artifact."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "v7b_comparison.json"
    destination.write_text(comparison.model_dump_json(indent=2), encoding="utf-8")
    return destination


def format_assessment_report(report: AssessmentEvaluationReport) -> str:
    """Render calculated values with N/A for unsupported dimensions."""
    lines = [
        f"Mode: {report.mode.value}",
        f"Profile: {report.configuration.execution_profile}",
        f"Cases: {report.evaluated_cases}/{report.total_cases}",
    ]
    lines.extend(
        f"{name.replace('_', ' ').title()}: {_display(getattr(report.aggregate_metrics, name))}"
        for name in METRIC_NAMES
    )
    lines.append(f"LLM judge calls: {report.llm_judge_calls}")
    lines.append(f"Deterministic fingerprint: {report.reproducibility_fingerprint}")
    return "\n".join(lines)


def format_assessment_comparison(comparison: AssessmentModeComparison) -> str:
    """Render aligned mode values without interpreting null as zero."""
    headings = [mode.value for mode in comparison.modes]
    lines = [f"{'Metric':<32}" + "".join(f"{item:>16}" for item in headings)]
    for row in comparison.rows:
        values = "".join(f"{_display(row.values.get(mode)):>16}" for mode in comparison.modes)
        lines.append(f"{row.metric:<32}{values}")
    if comparison.key_tradeoffs:
        lines.append("Key tradeoffs:")
        lines.extend(f"- {item}" for item in comparison.key_tradeoffs)
    return "\n".join(lines)


def _pareto_modes(
    cases: list[AssessmentCaseEvaluationResult],
) -> list[AssessmentEvaluationMode]:
    available = [item for item in cases if not item.failed]
    return [
        candidate.mode
        for candidate in available
        if not any(
            other.mode != candidate.mode and _dominates(other, candidate) for other in available
        )
    ]


def _dominates(
    candidate: AssessmentCaseEvaluationResult,
    baseline: AssessmentCaseEvaluationResult,
) -> bool:
    comparable: list[tuple[float, float]] = []
    for name in METRIC_NAMES:
        candidate_value = getattr(candidate.metrics, name)
        baseline_value = getattr(baseline.metrics, name)
        if candidate_value is None or baseline_value is None:
            continue
        if name == "unsupported_claim_rate":
            candidate_value = 1.0 - candidate_value
            baseline_value = 1.0 - baseline_value
        comparable.append((candidate_value, baseline_value))
    return (
        bool(comparable)
        and all(a >= b for a, b in comparable)
        and any(a > b for a, b in comparable)
    )


def _derive_tradeoffs(
    reports: dict[AssessmentEvaluationMode, AssessmentEvaluationReport],
    best_by_case: dict[str, list[AssessmentEvaluationMode]],
) -> list[str]:
    statements: list[str] = []
    ordered = list(AssessmentEvaluationMode)
    for baseline_mode, candidate_mode in pairwise(ordered):
        if baseline_mode not in reports or candidate_mode not in reports:
            continue
        baseline = reports[baseline_mode].aggregate_metrics
        candidate = reports[candidate_mode].aggregate_metrics
        for metric in ("risk_recall", "control_coverage", "governance_coverage"):
            before = getattr(baseline, metric)
            after = getattr(candidate, metric)
            if before is not None and after is not None and after > before:
                statements.append(
                    f"{candidate_mode.value} improved {metric} by {after - before:.3f} "
                    f"over {baseline_mode.value} on this synthetic benchmark."
                )
        for metric in (
            "human_oversight_accuracy",
            "architecture_fit_score",
            "groundedness",
        ):
            before = getattr(baseline, metric)
            after = getattr(candidate, metric)
            if before is not None and after is not None and after < before:
                statements.append(
                    f"{baseline_mode.value} retained a {before - after:.3f} advantage in "
                    f"{metric} over {candidate_mode.value} on this synthetic benchmark."
                )
        before_unsupported = baseline.unsupported_claim_rate
        after_unsupported = candidate.unsupported_claim_rate
        if (
            before_unsupported is not None
            and after_unsupported is not None
            and after_unsupported > before_unsupported
        ):
            statements.append(
                f"{baseline_mode.value} had a {after_unsupported - before_unsupported:.3f} "
                f"lower unsupported_claim_rate than {candidate_mode.value}."
            )
    simple_categories = {
        AssessmentScenarioCategory.LOW_RISK_PRODUCTIVITY,
        AssessmentScenarioCategory.SIMPLE_DETERMINISTIC,
    }
    deterministic = reports.get(AssessmentEvaluationMode.DETERMINISTIC)
    if deterministic is not None:
        simple_ids = [
            item.case_id
            for item in deterministic.cases
            if item.scenario_category in simple_categories
            and AssessmentEvaluationMode.DETERMINISTIC in best_by_case[item.case_id]
        ]
        if simple_ids:
            statements.append(
                "deterministic remained Pareto-optimal for simple cases: "
                + ", ".join(simple_ids)
                + "."
            )
    single = reports.get(AssessmentEvaluationMode.SINGLE_AGENT)
    multi = reports.get(AssessmentEvaluationMode.MULTI_AGENT)
    if single is not None and multi is not None:
        unchanged = [
            item.case_id
            for item in single.cases
            if not item.failed
            and not _case_by_id(multi, item.case_id).failed
            and _shared_final_quality_equal(item, _case_by_id(multi, item.case_id))
        ]
        if unchanged:
            statements.append(
                "multi_agent added no measurable final-output quality benefit over single_agent "
                "for: " + ", ".join(unchanged) + "."
            )
    return statements


def _shared_final_quality_equal(
    first: AssessmentCaseEvaluationResult,
    second: AssessmentCaseEvaluationResult,
) -> bool:
    final_metrics = (
        "risk_recall",
        "risk_precision",
        "severity_consistency",
        "control_coverage",
        "governance_coverage",
        "human_oversight_accuracy",
        "architecture_fit_score",
        "over_engineering_avoidance",
        "groundedness",
        "unsupported_claim_rate",
        "appropriate_abstention_rate",
    )
    return all(
        getattr(first.metrics, name) == getattr(second.metrics, name) for name in final_metrics
    )


def _case_by_id(
    report: AssessmentEvaluationReport,
    case_id: str,
) -> AssessmentCaseEvaluationResult:
    return next(item for item in report.cases if item.case_id == case_id)


def _display(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"
