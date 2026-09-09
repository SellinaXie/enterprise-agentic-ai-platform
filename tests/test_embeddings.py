"""OpenAI embeddings adapter tests with no network calls."""

from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, OpenAI

from app.core.exceptions import (
    EmbeddingNotConfiguredError,
    EmbeddingProviderError,
    InvalidEmbeddingError,
    OpenAIClientNotConfiguredError,
)
from app.rag.embeddings import OpenAIEmbeddingsService


def _response(*vectors: list[float]) -> SimpleNamespace:
    return SimpleNamespace(
        data=[
            SimpleNamespace(index=index, embedding=vector) for index, vector in enumerate(vectors)
        ]
    )


def test_embeddings_are_batched_and_ordered() -> None:
    client = Mock()
    client.embeddings.create.side_effect = [
        _response([1.0, 0.0, 0.0], [0.0, 1.0, 0.0]),
        _response([0.0, 0.0, 1.0]),
    ]
    service = OpenAIEmbeddingsService(
        model="text-embedding-3-small",
        dimension=3,
        batch_size=2,
        client_provider=lambda: cast(OpenAI, client),
    )

    vectors = service.embed_texts(["one", "two", "three"])

    assert vectors == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    assert client.embeddings.create.call_count == 2
    assert client.embeddings.create.call_args_list[0].kwargs == {
        "model": "text-embedding-3-small",
        "input": ["one", "two"],
        "dimensions": 3,
        "encoding_format": "float",
    }


def test_embedding_provider_failure_is_safe() -> None:
    client = Mock()
    client.embeddings.create.side_effect = APIConnectionError(
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    )
    service = OpenAIEmbeddingsService(
        model="text-embedding-3-small",
        dimension=3,
        client_provider=lambda: cast(OpenAI, client),
    )

    with pytest.raises(EmbeddingProviderError):
        service.embed_texts(["synthetic text"])


def test_missing_api_key_becomes_embedding_specific_error() -> None:
    service = OpenAIEmbeddingsService(
        model="text-embedding-3-small",
        dimension=3,
        client_provider=lambda: (_ for _ in ()).throw(OpenAIClientNotConfiguredError()),
    )

    with pytest.raises(EmbeddingNotConfiguredError):
        service.embed_texts(["synthetic text"])


@pytest.mark.parametrize(
    "response",
    [_response([1.0, 2.0]), _response([1.0, float("nan"), 2.0])],
)
def test_invalid_embedding_output_is_rejected(response: SimpleNamespace) -> None:
    client = Mock()
    client.embeddings.create.return_value = response
    service = OpenAIEmbeddingsService(
        model="text-embedding-3-small",
        dimension=3,
        client_provider=lambda: cast(OpenAI, client),
    )

    with pytest.raises(InvalidEmbeddingError):
        service.embed_texts(["synthetic text"])
