"""OpenAI client construction and structured assessment generation."""

from collections.abc import Callable
from functools import lru_cache
from time import perf_counter, sleep
from typing import Any

from openai import OpenAI, OpenAIError

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    OpenAIClientNotConfiguredError,
)
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.runtime.resilience import run_with_retry
from app.schemas.assessment import AssessmentResult
from app.services.assessment_prompt import AssessmentPrompt


def create_openai_client(settings: Settings) -> OpenAI:
    """Create an OpenAI client from validated runtime settings."""
    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value().strip():
        raise OpenAIClientNotConfiguredError

    return OpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.openai_timeout_seconds,
        max_retries=0,
    )


@lru_cache
def _get_default_openai_client() -> OpenAI:
    return create_openai_client(get_settings())


def get_openai_client(settings: Settings | None = None) -> OpenAI:
    """Lazily construct a client from supplied or process-level settings."""
    if settings is not None:
        return create_openai_client(settings)
    return _get_default_openai_client()


class OpenAIAssessmentGenerator:
    """Generate and validate one structured assessment with the Responses API."""

    def __init__(
        self,
        *,
        model: str,
        store_responses: bool = False,
        client_provider: Callable[[], OpenAI] = get_openai_client,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._model = model
        self._store_responses = store_responses
        self._client_provider = client_provider
        self._retry_policy = retry_policy
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics
        self._sleeper = sleeper

    def generate(self, prompt: AssessmentPrompt) -> AssessmentResult:
        """Return schema-constrained output while normalizing provider failures."""
        try:

            def request() -> Any:
                started = perf_counter()
                response = None
                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "input": [
                        {"role": "system", "content": prompt.system},
                        {"role": "user", "content": prompt.user},
                    ],
                    "text_format": AssessmentResult,
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

            response = (
                run_with_retry(
                    request,
                    policy=self._retry_policy,
                    sleeper=self._sleeper,
                    on_retry=(self._metrics.record_retry if self._metrics is not None else None),
                )
                if self._retry_policy is not None
                else request()
            )
        except OpenAIClientNotConfiguredError:
            raise
        except OpenAIError as exc:
            raise LLMProviderError from exc
        except (TypeError, ValueError) as exc:
            raise InvalidLLMResponseError from exc

        parsed_result = response.output_parsed
        if parsed_result is None:
            raise InvalidLLMResponseError

        try:
            return AssessmentResult.model_validate(parsed_result)
        except (TypeError, ValueError) as exc:
            raise InvalidLLMResponseError from exc
