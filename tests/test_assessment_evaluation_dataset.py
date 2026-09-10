"""V7B benchmark contract and finite-taxonomy integrity tests."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.evaluation.assessment.dataset import (
    AssessmentDatasetError,
    load_assessment_dataset,
)
from app.evaluation.assessment.models import (
    ArchitectureCharacteristic,
    AssessmentEvaluationDataset,
    AssessmentEvaluationMode,
    AssessmentScenarioCategory,
    EvaluationControlCategory,
    EvaluationRiskCategory,
)


def test_benchmark_has_ten_unique_synthetic_scenarios_and_all_modes() -> None:
    dataset = load_assessment_dataset()

    assert dataset.synthetic is True
    assert len(dataset.cases) == 10
    assert {item.scenario_category for item in dataset.cases} == set(AssessmentScenarioCategory)
    assert all(set(item.fixtures) == set(AssessmentEvaluationMode) for item in dataset.cases)
    assert "regulatory standard" in dataset.taxonomy_notice


def test_risk_and_control_taxonomies_are_finite_and_documented() -> None:
    assert {item.value for item in EvaluationRiskCategory} == {
        "privacy",
        "security",
        "model_risk",
        "hallucination_grounding",
        "compliance",
        "operational_risk",
        "access_control",
        "data_governance",
        "third_party_vendor_risk",
        "explainability",
        "human_oversight",
        "monitoring",
        "auditability",
    }
    assert {item.value for item in EvaluationControlCategory} == {
        "retrieval_grounding",
        "role_based_access_control",
        "least_privilege",
        "tool_allowlisting",
        "human_approval",
        "escalation",
        "audit_logging",
        "data_minimization",
        "model_monitoring",
        "output_validation",
        "fallback_behavior",
        "versioning",
        "approval_gates",
        "vendor_due_diligence",
        "incident_response",
    }


def test_duplicate_case_id_is_rejected() -> None:
    payload = load_assessment_dataset().model_dump(mode="json")
    payload["cases"][1]["case_id"] = payload["cases"][0]["case_id"]

    with pytest.raises(ValidationError, match="assessment case IDs must be unique"):
        AssessmentEvaluationDataset.model_validate(payload)


def test_unknown_taxonomy_value_is_rejected() -> None:
    payload = load_assessment_dataset().model_dump(mode="json")
    payload["cases"][0]["expected_risks"][0]["category"] = "imaginary_risk"

    with pytest.raises(ValidationError):
        AssessmentEvaluationDataset.model_validate(payload)


def test_duplicate_expectations_and_conflicting_risks_are_rejected() -> None:
    payload = load_assessment_dataset().model_dump(mode="json")
    first = payload["cases"][0]
    first["expected_controls"].append(first["expected_controls"][0])

    with pytest.raises(ValidationError, match="expected controls must be unique"):
        AssessmentEvaluationDataset.model_validate(payload)

    payload = load_assessment_dataset().model_dump(mode="json")
    first = payload["cases"][0]
    first["unacceptable_risks"].append(first["expected_risks"][0]["category"])
    with pytest.raises(ValidationError, match="must be disjoint"):
        AssessmentEvaluationDataset.model_validate(payload)


def test_invalid_evidence_reference_is_rejected() -> None:
    payload = load_assessment_dataset().model_dump(mode="json")
    requirement = payload["cases"][0]["evidence_requirements"][1]
    requirement["allowed_reference_ids"] = ["missing"]

    with pytest.raises(ValidationError, match="unavailable evidence"):
        AssessmentEvaluationDataset.model_validate(payload)


def test_invalid_architecture_expectation_and_missing_mode_are_rejected() -> None:
    payload = load_assessment_dataset().model_dump(mode="json")
    payload["cases"][0]["expected_architecture_characteristics"] = ["magic_architecture"]
    with pytest.raises(ValidationError):
        AssessmentEvaluationDataset.model_validate(payload)

    payload = load_assessment_dataset().model_dump(mode="json")
    del payload["cases"][0]["fixtures"][AssessmentEvaluationMode.MULTI_AGENT]
    with pytest.raises(ValidationError, match="all three execution modes"):
        AssessmentEvaluationDataset.model_validate(payload)


def test_required_abstention_contract_must_request_uncertainty_and_validation() -> None:
    payload = load_assessment_dataset().model_dump(mode="json")
    payload["cases"][0]["abstention"] = {"expectation": "required"}

    with pytest.raises(ValidationError, match="required abstention"):
        AssessmentEvaluationDataset.model_validate(payload)


def test_malformed_json_is_wrapped_as_dataset_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(AssessmentDatasetError):
        load_assessment_dataset(path)


def test_dataset_round_trip_is_stable_json() -> None:
    dataset = load_assessment_dataset()
    serialized = dataset.model_dump_json()
    restored = AssessmentEvaluationDataset.model_validate_json(serialized)

    assert restored == dataset
    assert ArchitectureCharacteristic.MULTI_AGENT_UNNECESSARY.value in json.dumps(
        restored.model_dump(mode="json")
    )
