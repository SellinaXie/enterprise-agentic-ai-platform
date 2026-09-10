"""Load and validate the version-controlled V7B synthetic benchmark."""

import json
from pathlib import Path

from pydantic import ValidationError

from app.evaluation.assessment.models import AssessmentEvaluationDataset

DEFAULT_ASSESSMENT_DATASET_PATH = (
    Path(__file__).parents[1] / "datasets" / "v7b_assessment_benchmark.json"
)


class AssessmentDatasetError(ValueError):
    """The V7B benchmark is unreadable or violates its typed contract."""


def load_assessment_dataset(
    path: Path = DEFAULT_ASSESSMENT_DATASET_PATH,
) -> AssessmentEvaluationDataset:
    """Read one UTF-8 JSON benchmark through its closed Pydantic schema."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return AssessmentEvaluationDataset.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise AssessmentDatasetError(f"Invalid V7B assessment benchmark: {path}") from exc
