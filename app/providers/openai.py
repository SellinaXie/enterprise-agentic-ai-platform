"""OpenAI SDK adapters. Vendor objects never cross this module boundary."""

import json
import math
from collections.abc import Callable
from functools import lru_cache
from time import perf_counter, sleep
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    EmbeddingNotConfiguredError,
    EmbeddingProviderError,
    InvalidEmbeddingError,
    InvalidLLMResponseError,
    LLMProviderError,
    OpenAIClientNotConfiguredError,
)
from app.providers.contracts import (
    ProviderCapabilities,
    ProviderName,
    ProviderPermanentError,
    ProviderTimeoutError,
    ProviderTransientError,
    StructuredModel,
    ToolCallDecision,
)
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.runtime.resilience import run_with_retry

OPENAI_CAPABILITIES = ProviderCapabilities(
    structured_output=True,
    tool_calling=True,
    usage_reporting=True,
    embeddings=True,
)


def create_openai_client(settings: Settings) -> OpenAI:
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
    return create_openai_client(settings) if settings is not None else _get_default_openai_client()


def close_openai_client() -> None:
    if _get_default_openai_client.cache_info().currsize:
        _get_default_openai_client().close()
    _get_default_openai_client.cache_clear()


def _normalize_provider_error(exc: Exception) -> Exception:
    if isinstance(exc, APITimeoutError):
        return ProviderTimeoutError()
    if isinstance(exc, RateLimitError | APIConnectionError | InternalServerError):
        return ProviderTransientError()
    if isinstance(exc, OpenAIError):
        return ProviderPermanentError()
    return exc


class OpenAIStructuredModelProvider:
    """Structured output and function-selection adapter for the Responses API."""

    name = ProviderName.OPENAI
    capabilities = OPENAI_CAPABILITIES

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
        self._model = model
        self._store_responses = store_responses
        self._client_provider = client_provider
        self._retry_policy = retry_policy
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics
        self._sleeper = sleeper

    def _run(self, operation: Callable[[], Any]) -> Any:
        try:
            return (
                run_with_retry(
                    operation,
                    policy=self._retry_policy,
                    sleeper=self._sleeper,
                    on_retry=(self._metrics.record_retry if self._metrics else None),
                )
                if self._retry_policy is not None
                else operation()
            )
        except OpenAIClientNotConfiguredError:
            raise
        except ProviderTimeoutError as exc:
            raise LLMProviderError from exc
        except ProviderTransientError as exc:
            raise LLMProviderError from exc
        except ProviderPermanentError as exc:
            raise LLMProviderError from exc
        except (TypeError, ValueError) as exc:
            raise InvalidLLMResponseError from exc

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        output_model: type[StructuredModel],
    ) -> StructuredModel:
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
            except Exception as exc:
                raise _normalize_provider_error(exc) from exc
            finally:
                if self._metrics is not None:
                    self._metrics.record_model_call(
                        max(0, round((perf_counter() - started) * 1_000)), response
                    )

        response = self._run(request)
        parsed = getattr(response, "output_parsed", None)
        if parsed is None:
            raise InvalidLLMResponseError
        try:
            return output_model.model_validate(parsed)
        except (TypeError, ValueError) as exc:
            raise InvalidLLMResponseError from exc

    def decide_tool_call(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        max_output_tokens: int = 200,
    ) -> ToolCallDecision | None:
        def request() -> Any:
            started = perf_counter()
            response = None
            kwargs: dict[str, Any] = {
                "model": self._model,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "tools": tools,
                "tool_choice": "auto",
                "parallel_tool_calls": False,
                "max_output_tokens": max_output_tokens,
                "store": self._store_responses,
            }
            if self._timeout_seconds is not None:
                kwargs["timeout"] = self._timeout_seconds
            try:
                response = self._client_provider().responses.create(**kwargs)
                return response
            except Exception as exc:
                raise _normalize_provider_error(exc) from exc
            finally:
                if self._metrics is not None:
                    self._metrics.record_model_call(
                        max(0, round((perf_counter() - started) * 1_000)), response
                    )

        response = self._run(request)
        calls = [
            item
            for item in getattr(response, "output", ())
            if getattr(item, "type", None) == "function_call"
        ]
        if not calls:
            return None
        call = calls[0]
        try:
            arguments = json.loads(call.arguments)
        except (json.JSONDecodeError, TypeError):
            arguments = {}
        return ToolCallDecision(
            name=str(call.name),
            arguments=arguments if isinstance(arguments, dict) else {},
        )


class OpenAIEmbeddingProvider:
    """Ordered, dimension-constrained embedding adapter."""

    name = ProviderName.OPENAI
    capabilities = OPENAI_CAPABILITIES

    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        batch_size: int = 100,
        client_provider: Callable[[], Any] = get_openai_client,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if dimension <= 0 or batch_size <= 0:
            raise ValueError("dimension and batch_size must be positive")
        self._model = model
        self._dimension = dimension
        self._batch_size = batch_size
        self._client_provider = client_provider
        self._retry_policy = retry_policy
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics
        self._sleeper = sleeper

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise InvalidEmbeddingError
        vectors: list[list[float]] = []
        try:
            client = self._client_provider()
            for start in range(0, len(texts), self._batch_size):
                batch = texts[start : start + self._batch_size]
                response = self._retry(lambda batch=batch: self._request_batch(client, batch))
                ordered = sorted(response.data, key=lambda item: item.index)
                vectors.extend([list(item.embedding) for item in ordered])
        except OpenAIClientNotConfiguredError as exc:
            raise EmbeddingNotConfiguredError from exc
        except ProviderTimeoutError as exc:
            raise EmbeddingProviderError from exc
        except ProviderTransientError as exc:
            raise EmbeddingProviderError from exc
        except ProviderPermanentError as exc:
            raise EmbeddingProviderError from exc
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidEmbeddingError from exc
        if len(vectors) != len(texts):
            raise InvalidEmbeddingError
        try:
            converted = [[float(value) for value in vector] for vector in vectors]
        except (TypeError, ValueError, OverflowError) as exc:
            raise InvalidEmbeddingError from exc
        if any(
            len(vector) != self._dimension or any(not math.isfinite(value) for value in vector)
            for vector in converted
        ):
            raise InvalidEmbeddingError
        return converted

    def _retry(self, operation: Callable[[], Any]) -> Any:
        return (
            run_with_retry(
                operation,
                policy=self._retry_policy,
                sleeper=self._sleeper,
                on_retry=(self._metrics.record_retry if self._metrics else None),
            )
            if self._retry_policy is not None
            else operation()
        )

    def _request_batch(self, client: Any, batch: list[str]) -> Any:
        started = perf_counter()
        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": batch,
            "dimensions": self._dimension,
            "encoding_format": "float",
        }
        if self._timeout_seconds is not None:
            kwargs["timeout"] = self._timeout_seconds
        try:
            return client.embeddings.create(**kwargs)
        except Exception as exc:
            raise _normalize_provider_error(exc) from exc
        finally:
            if self._metrics is not None:
                self._metrics.record_embedding_call(
                    max(0, round((perf_counter() - started) * 1_000))
                )
