"""OpenAI embeddings adapter with batching and strict dimension validation."""

import math
from collections.abc import Callable
from functools import partial
from time import perf_counter, sleep
from typing import Any, Protocol

from openai import OpenAI, OpenAIError

from app.core.exceptions import (
    EmbeddingNotConfiguredError,
    EmbeddingProviderError,
    InvalidEmbeddingError,
    OpenAIClientNotConfiguredError,
)
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy
from app.runtime.resilience import run_with_retry
from app.services.llm import get_openai_client


class EmbeddingsService(Protocol):
    """Provider-neutral embedding boundary used by ingestion and retrieval."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbeddingsService:
    """Generate float embeddings through OpenAI's synchronous embeddings API."""

    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        batch_size: int = 100,
        client_provider: Callable[[], OpenAI] = get_openai_client,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._model = model
        self._dimension = dimension
        self._batch_size = batch_size
        self._client_provider = client_provider
        self._retry_policy = retry_policy
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics
        self._sleeper = sleeper

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed non-empty text in bounded batches and preserve input order."""
        if not texts or any(not text.strip() for text in texts):
            raise InvalidEmbeddingError

        vectors: list[list[float]] = []
        try:
            client = self._client_provider()
            for start in range(0, len(texts), self._batch_size):
                batch = texts[start : start + self._batch_size]
                request = partial(self._request_batch, client, batch)

                response = (
                    run_with_retry(
                        request,
                        policy=self._retry_policy,
                        sleeper=self._sleeper,
                        on_retry=(
                            self._metrics.record_retry if self._metrics is not None else None
                        ),
                    )
                    if self._retry_policy is not None
                    else request()
                )
                ordered = sorted(response.data, key=lambda item: item.index)
                vectors.extend([list(item.embedding) for item in ordered])
        except OpenAIClientNotConfiguredError as exc:
            raise EmbeddingNotConfiguredError from exc
        except OpenAIError as exc:
            raise EmbeddingProviderError from exc
        except (AttributeError, TypeError, ValueError) as exc:
            raise InvalidEmbeddingError from exc

        if len(vectors) != len(texts):
            raise InvalidEmbeddingError
        try:
            converted = [[float(value) for value in vector] for vector in vectors]
        except (TypeError, ValueError, OverflowError) as exc:
            raise InvalidEmbeddingError from exc
        for vector in converted:
            if len(vector) != self._dimension or any(not math.isfinite(value) for value in vector):
                raise InvalidEmbeddingError
        return converted

    def _request_batch(self, client: OpenAI, batch: list[str]) -> Any:
        call_started = perf_counter()
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
        finally:
            if self._metrics is not None:
                self._metrics.record_embedding_call(
                    max(0, round((perf_counter() - call_started) * 1_000))
                )
