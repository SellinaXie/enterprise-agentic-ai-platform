"""OpenAI embeddings adapter with batching and strict dimension validation."""

import math
from collections.abc import Callable
from typing import Protocol

from openai import OpenAI, OpenAIError

from app.core.exceptions import (
    EmbeddingNotConfiguredError,
    EmbeddingProviderError,
    InvalidEmbeddingError,
    OpenAIClientNotConfiguredError,
)
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
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self._model = model
        self._dimension = dimension
        self._batch_size = batch_size
        self._client_provider = client_provider

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed non-empty text in bounded batches and preserve input order."""
        if not texts or any(not text.strip() for text in texts):
            raise InvalidEmbeddingError

        vectors: list[list[float]] = []
        try:
            client = self._client_provider()
            for start in range(0, len(texts), self._batch_size):
                response = client.embeddings.create(
                    model=self._model,
                    input=texts[start : start + self._batch_size],
                    dimensions=self._dimension,
                    encoding_format="float",
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
