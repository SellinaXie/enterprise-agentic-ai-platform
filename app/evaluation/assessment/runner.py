"""Run V7B architecture and risk-quality evaluation across existing modes."""

import argparse
import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.evaluation.assessment.dataset import (
    DEFAULT_ASSESSMENT_DATASET_PATH,
    load_assessment_dataset,
)
from app.evaluation.assessment.evaluators import (
    aggregate_quality_metrics,
    evaluate_assessment,
)
from app.evaluation.assessment.fixtures import DeterministicAssessmentFixtureExecutor
from app.evaluation.assessment.judges import AssessmentJudgeProtocol, OpenAIAssessmentJudge
from app.evaluation.assessment.models import (
    AssessmentCaseEvaluationResult,
    AssessmentEvaluationCase,
    AssessmentEvaluationConfiguration,
    AssessmentEvaluationDataset,
    AssessmentEvaluationMode,
    AssessmentEvaluationOutput,
    AssessmentEvaluationReport,
    AssessmentQualityMetrics,
    AssessmentRunStatus,
)
from app.evaluation.assessment.reports import (
    build_assessment_comparison,
    format_assessment_comparison,
    format_assessment_report,
    write_assessment_comparison,
    write_assessment_report,
)
from app.services.llm import get_openai_client


class AssessmentExecutorProtocol(Protocol):
    """Provider-neutral path for fixture or explicitly configured live execution."""

    def execute(
        self,
        case: AssessmentEvaluationCase,
        mode: AssessmentEvaluationMode,
    ) -> AssessmentEvaluationOutput: ...


class AssessmentEvaluationRunner:
    """Evaluate the same cases independently for one selected execution mode."""

    def __init__(
        self,
        *,
        dataset: AssessmentEvaluationDataset,
        executor: AssessmentExecutorProtocol,
        configuration: AssessmentEvaluationConfiguration,
        judge: AssessmentJudgeProtocol | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._dataset = dataset
        self._executor = executor
        self._configuration = configuration
        self._judge = judge
        self._clock = clock or (lambda: datetime.now(UTC))

    def run(self, mode: AssessmentEvaluationMode) -> AssessmentEvaluationReport:
        """Return calculated metrics while retaining failed and degraded cases."""
        results: list[AssessmentCaseEvaluationResult] = []
        judge_calls = 0
        judge_failures = 0
        for case in self._dataset.cases:
            try:
                output = self._executor.execute(case, mode)
                if output.run_status == AssessmentRunStatus.FAILED:
                    results.append(
                        AssessmentCaseEvaluationResult(
                            case_id=case.case_id,
                            scenario_category=case.scenario_category,
                            mode=mode,
                            failed=True,
                            error_code="assessment_mode_execution_failed",
                            metrics=AssessmentQualityMetrics(),
                        )
                    )
                    continue
                metrics, observations = evaluate_assessment(case, output)
            except Exception:
                results.append(
                    AssessmentCaseEvaluationResult(
                        case_id=case.case_id,
                        scenario_category=case.scenario_category,
                        mode=mode,
                        failed=True,
                        error_code="assessment_evaluation_execution_failed",
                        metrics=AssessmentQualityMetrics(),
                    )
                )
                continue
            judge_result = None
            if self._configuration.judge_enabled and self._judge is not None:
                judge_calls += 1
                try:
                    judge_result = self._judge.judge(case, output)
                except Exception:
                    judge_failures += 1
            results.append(
                AssessmentCaseEvaluationResult(
                    case_id=case.case_id,
                    scenario_category=case.scenario_category,
                    mode=mode,
                    metrics=metrics,
                    observations=observations,
                    judge=judge_result,
                )
            )

        evaluated = [item for item in results if not item.failed]
        failed = [item.case_id for item in results if item.failed]
        degraded = [
            item.case_id
            for item in evaluated
            if item.observations is not None
            and item.observations.run_status == AssessmentRunStatus.DEGRADED
        ]
        aggregate = aggregate_quality_metrics([item.metrics for item in evaluated])
        warnings = [
            "Synthetic deterministic assessment fixtures; not real-world production assurance.",
            "Deterministic metrics use explicit benchmark labels, not hidden reasoning.",
        ]
        if not self._configuration.judge_enabled:
            warnings.append("Optional LLM judge disabled; zero judge calls made.")
        elif self._judge is None:
            warnings.append("LLM judge enabled but unavailable; no judge results produced.")
        if judge_failures:
            warnings.append(f"LLM judge unavailable for {judge_failures} case(s).")
        return AssessmentEvaluationReport(
            generated_at=self._clock(),
            dataset_id=self._dataset.dataset_id,
            dataset_version=self._dataset.version,
            synthetic=self._dataset.synthetic,
            mode=mode,
            total_cases=len(results),
            evaluated_cases=len(evaluated),
            failed_cases=failed,
            degraded_cases=degraded,
            aggregate_metrics=aggregate,
            cases=results,
            configuration=self._configuration,
            llm_judge_calls=judge_calls,
            reproducibility_fingerprint=_fingerprint(mode, aggregate, results),
            warnings=warnings,
        )


def build_fixture_runner(
    dataset: AssessmentEvaluationDataset,
    settings: Settings,
    *,
    enable_judge: bool = False,
) -> AssessmentEvaluationRunner:
    """Wire network-free mode fixtures and an optional explicitly enabled judge."""
    judge = None
    judge_enabled = enable_judge and settings.evaluation_llm_judge_enabled
    if judge_enabled:
        judge = OpenAIAssessmentJudge(
            model=settings.evaluation_judge_model,
            store_responses=settings.openai_store_responses,
            client_provider=lambda: get_openai_client(settings),
        )
    return AssessmentEvaluationRunner(
        dataset=dataset,
        executor=DeterministicAssessmentFixtureExecutor(),
        judge=judge,
        configuration=AssessmentEvaluationConfiguration(
            execution_profile="deterministic_assessment_fixture",
            judge_enabled=judge_enabled,
            judge_model=settings.evaluation_judge_model if judge_enabled else None,
        ),
    )


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Run V7B modes and write machine-readable reports plus a comparison."""
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--mode", choices=[item.value for item in AssessmentEvaluationMode])
    selection.add_argument("--all", action="store_true", help="run all three modes")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_ASSESSMENT_DATASET_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/evaluation"))
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="enable only when EVALUATION_LLM_JUDGE_ENABLED=true and an API key exists",
    )
    arguments = parser.parse_args(argv)
    settings = Settings()
    if arguments.llm_judge and not settings.evaluation_llm_judge_enabled:
        parser.error("--llm-judge requires EVALUATION_LLM_JUDGE_ENABLED=true")
    if arguments.llm_judge and settings.openai_api_key is None:
        parser.error("--llm-judge requires OPENAI_API_KEY")

    dataset = load_assessment_dataset(arguments.dataset)
    runner = build_fixture_runner(dataset, settings, enable_judge=arguments.llm_judge)
    modes = (
        list(AssessmentEvaluationMode)
        if arguments.all
        else [AssessmentEvaluationMode(arguments.mode)]
    )
    reports = []
    for mode in modes:
        report = runner.run(mode)
        destination = write_assessment_report(report, arguments.output_dir)
        reports.append(report)
        print(format_assessment_report(report))
        print(f"Report: {destination}")
    if len(reports) > 1:
        comparison = build_assessment_comparison(reports)
        destination = write_assessment_comparison(comparison, arguments.output_dir)
        print(format_assessment_comparison(comparison))
        print(f"Comparison: {destination}")
    return 0


def _fingerprint(
    mode: AssessmentEvaluationMode,
    aggregate: AssessmentQualityMetrics,
    results: list[AssessmentCaseEvaluationResult],
) -> str:
    deterministic_payload = {
        "mode": mode,
        "aggregate": aggregate.model_dump(mode="json"),
        "cases": [item.model_dump(mode="json", exclude={"judge"}) for item in results],
    }
    encoded = json.dumps(deterministic_payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(run_cli())
