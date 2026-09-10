"""Version-controlled V7A benchmark integrity tests."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.dataset import EvaluationDatasetError, load_evaluation_dataset
from app.evaluation.models import EvaluationDataset


def test_benchmark_is_synthetic_reviewable_and_internally_consistent() -> None:
    dataset = load_evaluation_dataset()

    assert dataset.synthetic is True
    assert len(dataset.documents) == 8
    assert len(dataset.cases) == 9
    assert len({case.query_id for case in dataset.cases}) == 9
    assert any(case.query_type.value == "negative_no_answer" for case in dataset.cases)
    assert all("Synthetic" in document.title for document in dataset.documents)


def test_duplicate_query_ids_are_rejected() -> None:
    payload = load_evaluation_dataset().model_dump(mode="json")
    payload["cases"][1]["query_id"] = payload["cases"][0]["query_id"]

    with pytest.raises(ValidationError, match="query IDs must be unique"):
        EvaluationDataset.model_validate(payload)


def test_unknown_expected_evidence_is_rejected() -> None:
    payload = load_evaluation_dataset().model_dump(mode="json")
    payload["cases"][0]["expected"]["document_ids"].append("ffffffff-ffff-4fff-8fff-ffffffffffff")

    with pytest.raises(ValidationError, match="unknown expected document ID"):
        EvaluationDataset.model_validate(payload)


def test_duplicate_expected_evidence_is_rejected() -> None:
    payload = load_evaluation_dataset().model_dump(mode="json")
    expected_chunks = payload["cases"][0]["expected"]["chunk_ids"]
    expected_chunks.append(expected_chunks[0])

    with pytest.raises(ValidationError, match="expected chunk IDs must be unique"):
        EvaluationDataset.model_validate(payload)


def test_unknown_query_type_is_rejected_by_closed_vocabulary() -> None:
    payload = load_evaluation_dataset().model_dump(mode="json")
    payload["cases"][0]["query_type"] = "subjective_answer_quality"

    with pytest.raises(ValidationError, match="query_type"):
        EvaluationDataset.model_validate(payload)


def test_graph_query_requires_typed_entity_and_relationship_expectations() -> None:
    payload = load_evaluation_dataset().model_dump(mode="json")
    payload["cases"][1]["expected"]["relationships"] = []

    with pytest.raises(ValidationError, match="graph case lacks graph expectations"):
        EvaluationDataset.model_validate(payload)


def test_loader_normalizes_invalid_json_to_one_dataset_error(tmp_path: Path) -> None:
    dataset_path = tmp_path / "invalid.json"
    dataset_path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(EvaluationDatasetError, match="Invalid evaluation dataset"):
        load_evaluation_dataset(dataset_path)
