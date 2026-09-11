"""Provider-neutral structured-output boundary and compatibility adapter."""

from collections.abc import Callable
from time import sleep
from typing import Any

from app.providers.contracts import StructuredModel, StructuredModelProvider
from app.providers.openai import OpenAIStructuredModelProvider
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.services.llm import get_openai_client


class StructuredOutput:
    def __init__(self, provider: StructuredModelProvider) -> None:
        self._provider = provider

    def generate(
        self,
        *,
        system: str,
        user: str,
        output_model: type[StructuredModel],
    ) -> StructuredModel:
        return self._provider.generate_structured(
            system=system,
            user=user,
            output_model=output_model,
        )


class OpenAIStructuredOutput(StructuredOutput):
    """Preserve the established constructor for existing integrations."""

    def __init__(
        self,
        *,
        model: str,
        store_responses: bool,
        retry_limit: int,
        client_provider: Callable[[], Any] = get_openai_client,
        retry_base_delay_ms: int = 250,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        super().__init__(
            OpenAIStructuredModelProvider(
                model=model,
                store_responses=store_responses,
                client_provider=client_provider,
                retry_policy=RetryPolicy(
                    max_retries=retry_limit,
                    base_delay_ms=retry_base_delay_ms,
                ),
                timeout_seconds=timeout_seconds,
                metrics=metrics,
                sleeper=sleeper,
            )
        )
