"""OpenTelemetry-first export adapters for allowlisted operational metadata."""

from __future__ import annotations

from contextlib import suppress
from functools import lru_cache
from typing import Any, Protocol
from uuid import UUID

from app.runtime.models import OperationalTelemetry, QualityGateResult

_created_exporters: list[OperationalTelemetryExporter] = []


class OperationalTelemetryExporter(Protocol):
    """Export an assessment summary without prompts, documents, or model reasoning."""

    def export(
        self,
        *,
        assessment_id: UUID,
        telemetry: OperationalTelemetry,
        gate_result: QualityGateResult,
    ) -> None: ...

    def shutdown(self) -> None: ...


class NoOpTelemetryExporter:
    """Default adapter for local, test, and exporter-free deployments."""

    def export(
        self,
        *,
        assessment_id: UUID,
        telemetry: OperationalTelemetry,
        gate_result: QualityGateResult,
    ) -> None:
        del assessment_id, telemetry, gate_result

    def shutdown(self) -> None:
        return None


class OpenTelemetryExporter:
    """Emit a completed governance span through OTLP/HTTP."""

    def __init__(self, *, endpoint: str, service_name: str, timeout_seconds: int) -> None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=timeout_seconds))
        )
        self._provider = provider
        self._tracer = provider.get_tracer("enterprise_ai.runtime_governance")

    def export(
        self,
        *,
        assessment_id: UUID,
        telemetry: OperationalTelemetry,
        gate_result: QualityGateResult,
    ) -> None:
        attributes = safe_span_attributes(
            assessment_id=assessment_id,
            telemetry=telemetry,
            gate_result=gate_result,
        )
        with self._tracer.start_as_current_span("assessment.governance") as span:
            for key, value in attributes.items():
                span.set_attribute(key, value)

    def shutdown(self) -> None:
        self._provider.shutdown()


def safe_span_attributes(
    *,
    assessment_id: UUID,
    telemetry: OperationalTelemetry,
    gate_result: QualityGateResult,
) -> dict[str, Any]:
    """Return the explicit non-content attribute allowlist sent to exporters."""
    usage = telemetry.token_usage
    attributes: dict[str, Any] = {
        "assessment.id": str(assessment_id),
        "assessment.execution_mode": telemetry.execution_mode,
        "assessment.execution_health": telemetry.execution_health.value,
        "assessment.duration_ms": telemetry.total_duration_ms,
        "assessment.execution_duration_ms": telemetry.execution_duration_ms,
        "assessment.model_calls": telemetry.model_call_count or 0,
        "assessment.embedding_calls": telemetry.embedding_call_count or 0,
        "assessment.tool_calls": telemetry.tool_call_count,
        "assessment.retry_count": telemetry.retry_count,
        "assessment.timeout_count": telemetry.timeout_count,
        "assessment.degraded_state_count": telemetry.degraded_state_count,
        "assessment.review_status": telemetry.human_review_status.value,
        "assessment.termination_reason": telemetry.termination_reason,
        "assessment.gate_decision": gate_result.decision.value,
        "assessment.risk_level": gate_result.risk_level.value,
        "assessment.graph_retrieval_used": telemetry.graph_retrieval_used,
        "assessment.vector_retrieval_used": telemetry.vector_retrieval_used,
    }
    if telemetry.request_id is not None:
        attributes["request.id"] = telemetry.request_id
    if usage is not None:
        if usage.input_tokens is not None:
            attributes["gen_ai.usage.input_tokens"] = usage.input_tokens
        if usage.output_tokens is not None:
            attributes["gen_ai.usage.output_tokens"] = usage.output_tokens
    return attributes


@lru_cache
def build_telemetry_exporter(
    kind: str,
    endpoint: str | None,
    service_name: str,
    timeout_seconds: int,
) -> OperationalTelemetryExporter:
    """Build one process-level exporter from validated configuration."""
    if kind == "none":
        exporter: OperationalTelemetryExporter = NoOpTelemetryExporter()
    elif kind == "otlp" and endpoint is not None:
        exporter = OpenTelemetryExporter(
            endpoint=endpoint,
            service_name=service_name,
            timeout_seconds=timeout_seconds,
        )
    else:
        raise ValueError("Unsupported observability exporter configuration")
    _created_exporters.append(exporter)
    return exporter


def close_telemetry_exporters() -> None:
    """Flush process-level exporters during graceful shutdown."""
    for exporter in _created_exporters:
        with suppress(Exception):
            exporter.shutdown()
    _created_exporters.clear()
    build_telemetry_exporter.cache_clear()
