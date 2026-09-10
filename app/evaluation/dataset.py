"""Load and validate the version-controlled V7A benchmark dataset."""

import json
from pathlib import Path

from pydantic import ValidationError

from app.evaluation.models import EvaluationDataset

DEFAULT_DATASET_PATH = Path(__file__).with_name("datasets") / "v7a_retrieval_benchmark.json"


class EvaluationDatasetError(ValueError):
    """Raised when benchmark JSON cannot satisfy the closed dataset contract."""


def load_evaluation_dataset(path: Path = DEFAULT_DATASET_PATH) -> EvaluationDataset:
    """Read one UTF-8 JSON benchmark and reject malformed or inconsistent data."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return EvaluationDataset.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise EvaluationDatasetError(f"Invalid evaluation dataset: {path}") from exc
