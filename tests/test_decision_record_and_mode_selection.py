"""Block 2: decision-record export and demo-only per-request execution mode."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from fastapi.testclient import TestClient
from openai import OpenAI
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.api.dependencies import current_policy_description, get_assessment_generator
from app.core.config import Settings
from app.main import create_app
from app.repositories.assessments import AssessmentRepository
from app.repositories.runtime_reviews import RuntimeReviewRepository
from app.runtime.gate import RuntimeRiskGate
from app.runtime.models import HumanReviewRequest, RuntimeRiskPolicy
from app.services.llm import OpenAIAssessmentGenerator
from app.services.runtime_governance import RuntimeGovernanceService
from tests.factories import build_assessment_result
from tests.test_governance_core import (
    AUDIENCE,
    CREATOR,
    ISSUER,
    REVIEWER,
    SECRET,
    _pending_assessment,
    _principal,
    _request,
    _token,
)


def _settings(database_url: str, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "APP_ENV": "test",
        "APP_LOG_LEVEL": "ERROR",
        "DATABASE_URL": database_url,
        "RUNTIME_RISK_GATE_ENABLED": True,
        "AUTH_ENABLED": True,
        "AUTH_JWT_SECRET": SECRET,
        "AUTH_JWT_ISSUER": ISSUER,
        "AUTH_JWT_AUDIENCE": AUDIENCE,
        "PROVIDER_REQUIRED": False,
        "EXECUTION_ROUTING_ENABLED": False,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def _client(settings: Settings) -> TestClient:
    openai_client = Mock()
    openai_client.responses.parse.return_value = SimpleNamespace(
        output_parsed=build_assessment_result()
    )
    generator = OpenAIAssessmentGenerator(
        model="gpt-4.1-mini", client_provider=lambda: cast(OpenAI, openai_client)
    )
    application = create_app(settings)
    application.dependency_overrides[get_assessment_generator] = lambda: generator
    return TestClient(application)


def test_decision_record_is_complete_and_fingerprint_is_stable(db_session: Session) -> None:
    service = RuntimeGovernanceService(
        assessments=AssessmentRepository(db_session),
        reviews=RuntimeReviewRepository(db_session),
        gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        enforce_separation_of_duties=True,
        policy_fingerprint="sha256:policy-under-test",
    )
    assessment_id = _pending_assessment(service, AssessmentRepository(db_session))

    pending = service.build_decision_record(assessment_id)
    pending_again = service.build_decision_record(assessment_id)
    service.approve(assessment_id, HumanReviewRequest(comment="OK"), principal=_principal(REVIEWER))
    approved = service.build_decision_record(assessment_id)

    assert pending.record_fingerprint == pending_again.record_fingerprint
    assert pending.record_fingerprint != approved.record_fingerprint
    assert pending.evidence_source == "latest_candidate"
    assert pending.outcome.result is None
    assert approved.evidence_source == "final_result"
    assert approved.outcome.status == "completed"
    assert approved.input.created_by_subject == CREATOR
    assert approved.routing.execution_mode == "deterministic"
    assert approved.candidate_versions[0].policy_fingerprint == "sha256:policy-under-test"
    assert approved.current_policy_fingerprint == "sha256:policy-under-test"
    assert [review.action for review in approved.reviews] == ["requested", "approved"]
    assert approved.reviews[1].reviewer_subject == REVIEWER
    assert "reviewer_email" not in approved.model_dump()["reviews"][1]


def test_api_decision_record_is_reviewer_only(database_url: str, engine: Engine) -> None:
    del engine
    settings = _settings(database_url)
    with _client(settings) as client:
        created = client.post(
            "/api/v1/assessments",
            json=_request().model_dump(mode="json"),
            headers=_token(CREATOR, ["analyst"]),
        ).json()
        path = f"/api/v1/assessments/{created['assessment_id']}/decision-record"
        as_analyst = client.get(path, headers=_token(CREATOR, ["analyst"]))
        as_reviewer = client.get(path, headers=_token(REVIEWER, ["reviewer"]))
        policy = client.get("/api/v1/governance/policy", headers=_token(REVIEWER, ["reviewer"]))

    assert as_analyst.status_code == 403
    assert as_reviewer.status_code == 200
    record = as_reviewer.json()
    assert record["record_version"] == 1
    assert record["record_fingerprint"].startswith("sha256:")
    assert record["current_policy_fingerprint"] == policy.json()["policy_fingerprint"]
    assert (
        record["candidate_versions"][0]["policy_fingerprint"]
        == record["current_policy_fingerprint"]
    )
    assert record["current_policy_fingerprint"] == (
        current_policy_description(settings).policy_fingerprint
    )


def test_execution_mode_selection_is_rejected_unless_enabled(
    database_url: str, engine: Engine
) -> None:
    del engine
    with _client(_settings(database_url)) as client:
        rejected = client.post(
            "/api/v1/assessments?execution_mode=deterministic",
            json=_request().model_dump(mode="json"),
            headers=_token(CREATOR, ["analyst"]),
        )
        policy = client.get("/api/v1/governance/policy", headers=_token(CREATOR, ["analyst"]))

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "execution_mode_selection_disabled"
    assert policy.json()["execution_mode_selection_enabled"] is False


def test_requested_mode_falls_back_honestly_when_capability_is_missing(
    database_url: str, engine: Engine
) -> None:
    del engine
    settings = _settings(database_url, EXECUTION_MODE_SELECTION_ENABLED=True)
    with _client(settings) as client:
        created = client.post(
            "/api/v1/assessments?execution_mode=multi_agent",
            json=_request().model_dump(mode="json"),
            headers=_token(CREATOR, ["analyst"]),
        )
        invalid = client.post(
            "/api/v1/assessments?execution_mode=autonomous",
            json=_request().model_dump(mode="json"),
            headers=_token(CREATOR, ["analyst"]),
        )
        record = client.get(
            f"/api/v1/assessments/{created.json()['assessment_id']}/decision-record",
            headers=_token(REVIEWER, ["reviewer"]),
        ).json()
        policy = client.get("/api/v1/governance/policy", headers=_token(CREATOR, ["analyst"]))

    assert created.status_code == 200
    assert invalid.status_code == 422
    assert policy.json()["execution_mode_selection_enabled"] is True
    assert record["routing"]["preferred_execution_mode"] == "multi_agent"
    assert record["routing"]["execution_mode"] == "deterministic"
    assert record["routing"]["routing_reason_codes"] == ["caller_requested_mode"]
    assert "fallback_to_deterministic" in record["routing"]["fallback_reason_codes"]
    assert "execution_mode" not in record["input"]["request"]
