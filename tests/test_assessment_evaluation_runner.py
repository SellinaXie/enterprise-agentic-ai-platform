"""V7B three-mode runner, reporting, failure, and reproducibility tests."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.core.config import Settings
from app.evaluation.assessment.dataset import load_assessment_dataset
from app.evaluation.assessment.models import (
    AssessmentEvaluationMode,
    AssessmentEvaluationReport,
)
from app.evaluation.assessment.reports import (
    build_assessment_comparison,
    format_assessment_comparison,
)
from app.evaluation.assessment.runner import (
    AssessmentEvaluationRunner,
    build_fixture_runner,
    run_cli,
)


@pytest.fixture
def reports() -> dict[AssessmentEvaluationMode, AssessmentEvaluationReport]:
    dataset = load_assessment_dataset()
    runner = build_fixture_runner(dataset, Settings(_env_file=None))
    return {mode: runner.run(mode) for mode in AssessmentEvaluationMode}


def test_all_modes_evaluate_the_same_ten_cases_with_correct_labels(
    reports: dict[AssessmentEvaluationMode, AssessmentEvaluationReport],
) -> None:
    case_ids = [{item.case_id for item in report.cases} for report in reports.values()]

    assert all(report.evaluated_cases == 10 for report in reports.values())
    assert case_ids[0] == case_ids[1] == case_ids[2]
    assert all(item.mode == mode for mode, report in reports.items() for item in report.cases)
    assert all(report.skipped_cases == [] for report in reports.values())


def test_metrics_aggregate_independently_and_do_not_hardcode_a_winner(
    reports: dict[AssessmentEvaluationMode, AssessmentEvaluationReport],
) -> None:
    deterministic = reports[AssessmentEvaluationMode.DETERMINISTIC].aggregate_metrics
    single = reports[AssessmentEvaluationMode.SINGLE_AGENT].aggregate_metrics
    multi = reports[AssessmentEvaluationMode.MULTI_AGENT].aggregate_metrics

    assert deterministic.risk_recall < single.risk_recall < multi.risk_recall
    assert deterministic.control_coverage < single.control_coverage < multi.control_coverage
    assert deterministic.governance_coverage < single.governance_coverage
    assert multi.specialist_preservation == 1.0
    assert deterministic.specialist_preservation is None
    assert single.specialist_preservation is None


def test_simple_cases_expose_over_engineering_in_agent_modes(
    reports: dict[AssessmentEvaluationMode, AssessmentEvaluationReport],
) -> None:
    def case_metric(mode: AssessmentEvaluationMode, case_id: str, name: str) -> Any:
        result = next(item for item in reports[mode].cases if item.case_id == case_id)
        return getattr(result.metrics, name)

    for case_id in ("case08_low_risk_productivity", "case10_simple_rules_workflow"):
        assert (
            case_metric(
                AssessmentEvaluationMode.DETERMINISTIC,
                case_id,
                "over_engineering_avoidance",
            )
            == 1.0
        )
        assert (
            case_metric(
                AssessmentEvaluationMode.MULTI_AGENT,
                case_id,
                "over_engineering_avoidance",
            )
            == 0.0
        )


def test_multi_agent_degraded_cases_remain_visible_and_transparent(
    reports: dict[AssessmentEvaluationMode, AssessmentEvaluationReport],
) -> None:
    multi = reports[AssessmentEvaluationMode.MULTI_AGENT]

    assert multi.degraded_cases == [
        "case02_confidential_internal_rag",
        "case06_compliance_review",
        "case09_insufficient_information",
    ]
    assert multi.aggregate_metrics.synthesis_transparency == 1.0
    assert multi.failed_cases == []


def test_comparison_preserves_null_and_pareto_ties(
    reports: dict[AssessmentEvaluationMode, AssessmentEvaluationReport],
) -> None:
    comparison = build_assessment_comparison(list(reports.values()))
    rows = {item.metric: item.values for item in comparison.rows}

    assert rows["specialist_preservation"][AssessmentEvaluationMode.DETERMINISTIC] is None
    assert rows["specialist_preservation"][AssessmentEvaluationMode.MULTI_AGENT] == 1.0
    assert (
        AssessmentEvaluationMode.DETERMINISTIC
        in comparison.best_mode_by_case["case10_simple_rules_workflow"]
    )
    assert comparison.benchmark_scope["production_assurance"] is False
    assert any(
        "no measurable final-output quality benefit" in item for item in comparison.key_tradeoffs
    )
    assert any("unsupported_claim_rate" in item for item in comparison.key_tradeoffs)
    assert "N/A" in format_assessment_comparison(comparison)


def test_comparison_rejects_mismatched_case_sets(
    reports: dict[AssessmentEvaluationMode, AssessmentEvaluationReport],
) -> None:
    first = reports[AssessmentEvaluationMode.DETERMINISTIC]
    second = reports[AssessmentEvaluationMode.SINGLE_AGENT].model_copy(
        update={"cases": reports[AssessmentEvaluationMode.SINGLE_AGENT].cases[:-1]}
    )

    with pytest.raises(ValueError, match="same benchmark cases"):
        build_assessment_comparison([first, second])


def test_deterministic_fingerprints_and_case_metrics_repeat_exactly() -> None:
    dataset = load_assessment_dataset()
    runner = build_fixture_runner(dataset, Settings(_env_file=None))

    first = runner.run(AssessmentEvaluationMode.MULTI_AGENT)
    second = runner.run(AssessmentEvaluationMode.MULTI_AGENT)

    assert first.reproducibility_fingerprint == second.reproducibility_fingerprint
    assert first.aggregate_metrics == second.aggregate_metrics
    assert first.cases == second.cases


def test_configuration_and_reports_exclude_api_keys_database_urls_and_prompts() -> None:
    dataset = load_assessment_dataset()
    runner = build_fixture_runner(
        dataset,
        Settings(
            _env_file=None,
            OPENAI_API_KEY="synthetic-secret-value",
            DATABASE_URL="postgresql+psycopg://localhost/example_test",
        ),
    )

    serialized = runner.run(AssessmentEvaluationMode.DETERMINISTIC).model_dump_json()

    assert "synthetic-secret-value" not in serialized
    assert "postgresql+psycopg://localhost/example_test" not in serialized
    assert "system prompt" not in serialized.casefold()
    assert "chain_of_thought" not in serialized


def test_executor_failure_is_reported_without_exception_content() -> None:
    dataset = load_assessment_dataset()

    class FailingExecutor:
        def execute(self, *_: object):  # noqa: ANN202
            raise RuntimeError("secret provider detail")

    runner = AssessmentEvaluationRunner(
        dataset=dataset,
        executor=FailingExecutor(),
        configuration=build_fixture_runner(dataset, Settings(_env_file=None))._configuration,  # noqa: SLF001
    )

    report = runner.run(AssessmentEvaluationMode.DETERMINISTIC)

    assert report.evaluated_cases == 0
    assert len(report.failed_cases) == 10
    assert all(item.error_code == "assessment_evaluation_execution_failed" for item in report.cases)
    assert "secret provider detail" not in report.model_dump_json()


def test_cli_writes_stable_machine_readable_reports_and_portfolio_comparison(
    tmp_path: Path,
) -> None:
    exit_code = run_cli(["--all", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    for mode in AssessmentEvaluationMode:
        payload = json.loads((tmp_path / f"v7b_{mode.value}.json").read_text(encoding="utf-8"))
        assert payload["mode"] == mode.value
        assert payload["configuration"]["judge_enabled"] is False
        assert payload["llm_judge_calls"] == 0
    comparison = json.loads((tmp_path / "v7b_comparison.json").read_text(encoding="utf-8"))
    assert set(comparison) >= {
        "modes",
        "key_tradeoffs",
        "best_mode_by_case",
        "benchmark_scope",
    }


def test_comparison_serialization_is_stable_except_generation_time(
    reports: dict[AssessmentEvaluationMode, AssessmentEvaluationReport],
) -> None:
    first = build_assessment_comparison(list(reports.values()))
    second = build_assessment_comparison(list(reports.values()))

    assert first.model_copy(update={"generated_at": second.generated_at}) == second
