"""Validation tests for V5 specialist handoff contracts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.multi_agent_models import (
    ArchitectureRecommendation,
    EvidenceBrief,
    EvidenceItem,
    RiskGovernanceReview,
    SpecialistConfidence,
)
from tests.factories import (
    build_architecture_recommendation,
    build_evidence_brief,
    build_risk_governance_review,
)


def test_all_specialist_contracts_validate_and_use_qualitative_confidence() -> None:
    evidence = build_evidence_brief()
    architecture = build_architecture_recommendation()
    risk = build_risk_governance_review()

    assert isinstance(evidence, EvidenceBrief)
    assert isinstance(architecture, ArchitectureRecommendation)
    assert isinstance(risk, RiskGovernanceReview)
    assert {evidence.confidence, architecture.confidence, risk.confidence} <= set(
        SpecialistConfidence
    )


def test_contracts_reject_extra_fields_and_invalid_confidence() -> None:
    payload = build_evidence_brief().model_dump()
    payload["private_reasoning"] = "must not be accepted"
    with pytest.raises(ValidationError):
        EvidenceBrief.model_validate(payload)

    payload = build_architecture_recommendation().model_dump()
    payload["confidence"] = 0.87
    with pytest.raises(ValidationError):
        ArchitectureRecommendation.model_validate(payload)


def test_evidence_item_rejects_undeclared_provenance() -> None:
    with pytest.raises(ValidationError, match="undeclared chunk"):
        EvidenceBrief(
            summary="Synthetic brief.",
            evidence_items=[
                EvidenceItem(
                    claim="A control exists.",
                    supporting_chunk_ids=[uuid4()],
                    relevance="Relevant to governance.",
                )
            ],
            evidence_gaps=[],
            confidence="medium",
        )


def test_optional_evidence_and_architecture_collections_default_cleanly() -> None:
    brief = EvidenceBrief(
        summary="No relevant evidence was found.",
        confidence="low",
    )
    architecture_payload = build_architecture_recommendation().model_dump()
    architecture_payload.pop("integrations")

    assert brief.evidence_items == []
    assert brief.evidence_gaps == []
    assert ArchitectureRecommendation.model_validate(architecture_payload).integrations == []


def test_risk_contract_rejects_malformed_nested_oversight() -> None:
    payload = build_risk_governance_review().model_dump()
    payload["human_oversight"] = {"review_required": "sometimes"}

    with pytest.raises(ValidationError):
        RiskGovernanceReview.model_validate(payload)
