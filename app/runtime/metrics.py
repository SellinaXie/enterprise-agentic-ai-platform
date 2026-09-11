"""Request-scoped, payload-free provider operation counters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.runtime.models import FailureCategory, ProviderTokenUsage


@dataclass(slots=True)
class RuntimeMetricsRecorder:
    """Collect only counters, durations, and provider-reported token usage."""

    model_call_durations_ms: list[int] = field(default_factory=list)
    embedding_call_durations_ms: list[int] = field(default_factory=list)
    tool_call_durations_ms: list[int] = field(default_factory=list)
    retry_count: int = 0
    timeout_count: int = 0
    _input_tokens: int = 0
    _output_tokens: int = 0
    _total_tokens: int = 0
    _usage_observed: bool = False

    def record_model_call(self, duration_ms: int, response: Any | None = None) -> None:
        self.model_call_durations_ms.append(max(0, duration_ms))
        self._record_usage(response)

    def record_embedding_call(self, duration_ms: int) -> None:
        self.embedding_call_durations_ms.append(max(0, duration_ms))

    def record_tool_call(self, duration_ms: int) -> None:
        self.tool_call_durations_ms.append(max(0, duration_ms))

    def record_retry(self, _: int, category: FailureCategory) -> None:
        self.retry_count += 1
        if category == FailureCategory.TIMEOUT:
            self.timeout_count += 1

    @property
    def token_usage(self) -> ProviderTokenUsage | None:
        if not self._usage_observed:
            return None
        return ProviderTokenUsage(
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
            total_tokens=self._total_tokens,
        )

    def _record_usage(self, response: Any | None) -> None:
        if isinstance(response, ProviderTokenUsage):
            self._usage_observed = True
            self._input_tokens += response.input_tokens
            self._output_tokens += response.output_tokens
            self._total_tokens += response.total_tokens
            return
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if (
            total_tokens is None
            and isinstance(input_tokens, int)
            and isinstance(output_tokens, int)
        ):
            total_tokens = input_tokens + output_tokens
        values = (input_tokens, output_tokens, total_tokens)
        if not all(isinstance(value, int) and value >= 0 for value in values):
            return
        self._usage_observed = True
        self._input_tokens += values[0]
        self._output_tokens += values[1]
        self._total_tokens += values[2]
