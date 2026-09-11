"""Shared OpenAI structured-output adapter for typed V5 specialist calls."""

from collections.abc import Callable
from time import perf_counter, sleep
from typing import Any, TypeVar

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    OpenAIClientNotConfiguredError,
)
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.runtime.resilience import run_with_retry

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class OpenAIStructuredOutput:
    """Generate one closed Pydantic contract with a small bounded retry."""

    def __init__(
        self,
        *,
        model: str,
        store_responses: bool,
        retry_limit: int,
        client_provider: Callable[[], OpenAI],
        retry_base_delay_ms: int = 250,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._model = model
        self._store_responses = store_responses
        self._retry_policy = RetryPolicy(
            max_retries=retry_limit,
            base_delay_ms=retry_base_delay_ms,
        )
        self._client_provider = client_provider
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics
        self._sleeper = sleeper

    def generate(
        self,
        *,
        system: str,
        user: str,
        output_model: type[StructuredModel],
    ) -> StructuredModel:
        """Return a validated model or the existing safe provider/application error."""

        def request() -> Any:
            started = perf_counter()
            response = None
            kwargs: dict[str, Any] = {
                "model": self._model,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "text_format": output_model,
                "store": self._store_responses,
            }
            if self._timeout_seconds is not None:
                kwargs["timeout"] = self._timeout_seconds
            try:
                response = self._client_provider().responses.parse(**kwargs)
                return response
            finally:
                if self._metrics is not None:
                    self._metrics.record_model_call(
                        max(0, round((perf_counter() - started) * 1_000)), response
                    )

        try:
            response = run_with_retry(
                request,
                policy=self._retry_policy,
                sleeper=self._sleeper,
                on_retry=(self._metrics.record_retry if self._metrics is not None else None),
            )
        except OpenAIClientNotConfiguredError:
            raise
        except OpenAIError as exc:
            raise LLMProviderError from exc
        parsed = response.output_parsed
        if parsed is None:
            raise InvalidLLMResponseError
        try:
            return output_model.model_validate(parsed)
        except (TypeError, ValueError) as exc:
            raise InvalidLLMResponseError from exc
