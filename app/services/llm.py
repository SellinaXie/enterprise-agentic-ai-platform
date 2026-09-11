"""Provider-neutral assessment generation with V1-compatible OpenAI exports."""

from collections.abc import Callable
from time import sleep
from typing import Any

from app.providers.contracts import StructuredModelProvider
from app.providers.openai import (
    OpenAIStructuredModelProvider,
    close_openai_client,
    create_openai_client,
    get_openai_client,
)
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.schemas.assessment import AssessmentResult
from app.services.assessment_prompt import AssessmentPrompt


class ProviderAssessmentGenerator:
    """Generate assessments through the narrow structured-model contract."""

    def __init__(self, provider: StructuredModelProvider) -> None:
        self._provider = provider

    def generate(self, prompt: AssessmentPrompt) -> AssessmentResult:
        return self._provider.generate_structured(
            system=prompt.system,
            user=prompt.user,
            output_model=AssessmentResult,
        )


class OpenAIAssessmentGenerator(ProviderAssessmentGenerator):
    """Backward-compatible constructor backed by the OpenAI provider adapter."""

    def __init__(
        self,
        *,
        model: str,
        store_responses: bool = False,
        client_provider: Callable[[], Any] = get_openai_client,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        super().__init__(
            OpenAIStructuredModelProvider(
                model=model,
                store_responses=store_responses,
                client_provider=client_provider,
                retry_policy=retry_policy,
                timeout_seconds=timeout_seconds,
                metrics=metrics,
                sleeper=sleeper,
            )
        )


__all__ = [
    "OpenAIAssessmentGenerator",
    "ProviderAssessmentGenerator",
    "close_openai_client",
    "create_openai_client",
    "get_openai_client",
]
