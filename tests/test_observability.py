"""Privacy-safe exporter boundary tests."""

import json
from unittest.mock import Mock
from uuid import uuid4

from app.agents.models import DeterministicExecutionMetadata
from app.models.assessment import RiskSeverity
from app.observability.exporters import safe_span_attributes
from app.runtime.gate import RuntimeRiskGate
from app.runtime.models import RuntimeRiskDecision, RuntimeRiskPolicy
from app.runtime.telemetry import build_operational_telemetry
from app.services.runtime_governance import RuntimeGovernanceService
from tests.factories import build_assessment_result


def test_export_attributes_are_an_explicit_content_free_allowlist() -> None:
    gate_result = RuntimeRiskGate(RuntimeRiskPolicy()).evaluate(
        RuntimeGovernanceService.derive_signals(
            result=build_assessment_result(),
            evidence=(),
            execution=DeterministicExecutionMetadata(),
            provenance_valid=True,
        )
    )
    telemetry = build_operational_telemetry(
        execution=DeterministicExecutionMetadata(),
        duration_ms=12,
        gate_decision=RuntimeRiskDecision.REQUIRE_HUMAN_REVIEW,
        request_id="safe-request-id",
    )

    attributes = safe_span_attributes(
        assessment_id=uuid4(), telemetry=telemetry, gate_result=gate_result
    )

    assert attributes["request.id"] == "safe-request-id"
    assert attributes["assessment.execution_mode"] == "deterministic"
    assert set(attributes) <= {
        "assessment.id",
        "assessment.execution_mode",
        "assessment.execution_health",
        "assessment.duration_ms",
        "assessment.execution_duration_ms",
        "assessment.model_calls",
        "assessment.embedding_calls",
        "assessment.tool_calls",
        "assessment.retry_count",
        "assessment.timeout_count",
        "assessment.degraded_state_count",
        "assessment.review_status",
        "assessment.termination_reason",
        "assessment.gate_decision",
        "assessment.risk_level",
        "assessment.graph_retrieval_used",
        "assessment.vector_retrieval_used",
        "request.id",
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.output_tokens",
    }
    encoded = json.dumps(attributes).lower()
    for forbidden in ("prompt", "document", "embedding_vector", "chain_of_thought", "secret"):
        assert forbidden not in encoded


def test_export_failure_does_not_change_governance_outcome() -> None:
    exporter = Mock()
    exporter.export.side_effect = RuntimeError("synthetic collector outage")
    assessments = Mock()
    reviews = Mock()
    persisted = Mock(status="completed")
    assessments.mark_completed.return_value = persisted
    service = RuntimeGovernanceService(
        assessments=assessments,
        reviews=reviews,
        gate=RuntimeRiskGate(RuntimeRiskPolicy()),
        telemetry_exporter=exporter,
    )

    result = build_assessment_result()
    result = result.model_copy(
        update={"risks": [result.risks[0].model_copy(update={"severity": RiskSeverity.LOW})]}
    )
    outcome = service.process_candidate(
        assessment_id=uuid4(),
        result=result,
        evidence=(),
        execution=DeterministicExecutionMetadata(),
        duration_ms=1,
    )

    assert outcome is persisted
    exporter.export.assert_called_once()
