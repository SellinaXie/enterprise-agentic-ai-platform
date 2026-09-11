"""Privacy and field-accuracy tests for structured runtime telemetry."""

import json
from types import SimpleNamespace

from app.agents.models import DeterministicExecutionMetadata
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import ProviderTokenUsage, RuntimeRiskDecision
from app.runtime.telemetry import build_operational_telemetry


def test_telemetry_tracks_known_values_and_never_fabricates_cost() -> None:
    telemetry = build_operational_telemetry(
        execution=DeterministicExecutionMetadata(),
        duration_ms=42,
        gate_decision=RuntimeRiskDecision.AUTO_COMPLETE,
        token_usage=ProviderTokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
    )

    assert telemetry.total_duration_ms == 42
    assert telemetry.model_call_count == 1
    assert telemetry.tool_call_count == 0
    assert telemetry.token_usage is not None
    assert telemetry.token_usage.total_tokens == 150
    assert telemetry.estimated_cost is None
    assert telemetry.events[-1].event_type == "quality_gate_evaluated"


def test_cost_is_calculated_only_from_explicit_pricing() -> None:
    telemetry = build_operational_telemetry(
        execution=DeterministicExecutionMetadata(),
        duration_ms=1,
        gate_decision=RuntimeRiskDecision.COMPLETE_WITH_WARNING,
        token_usage=ProviderTokenUsage(input_tokens=1_000_000, output_tokens=500_000),
        input_cost_per_million=2,
        output_cost_per_million=4,
    )

    assert telemetry.estimated_cost == 4
    assert telemetry.estimated_cost_currency == "USD"


def test_metrics_recorder_aggregates_only_provider_reported_usage() -> None:
    recorder = RuntimeMetricsRecorder()
    recorder.record_model_call(
        3,
        SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=4, total_tokens=14)),
    )
    recorder.record_model_call(
        5,
        SimpleNamespace(usage=SimpleNamespace(input_tokens=6, output_tokens=2, total_tokens=8)),
    )

    assert recorder.model_call_durations_ms == [3, 5]
    assert recorder.token_usage == ProviderTokenUsage(
        input_tokens=16, output_tokens=6, total_tokens=22
    )


def test_telemetry_contract_has_no_sensitive_payload_fields() -> None:
    payload = json.dumps(
        build_operational_telemetry(
            execution=DeterministicExecutionMetadata(),
            duration_ms=1,
            gate_decision=RuntimeRiskDecision.AUTO_COMPLETE,
        ).model_dump(mode="json")
    )

    for forbidden in (
        "prompt_text",
        "chain_of_thought",
        "embedding_vector",
        "source_document_content",
        "api_secret",
    ):
        assert forbidden not in payload.lower()
