"""Small built-in provider selection; this is deliberately not a plugin system."""

from functools import partial

from app.core.config import Settings
from app.providers.anthropic import AnthropicStructuredModelProvider, get_anthropic_client
from app.providers.contracts import EmbeddingProvider, StructuredModelProvider
from app.providers.openai import (
    OpenAIEmbeddingProvider,
    OpenAIStructuredModelProvider,
    get_openai_client,
)
from app.runtime.metrics import RuntimeMetricsRecorder
from app.runtime.models import RetryPolicy


def build_structured_model_provider(
    settings: Settings,
    *,
    metrics: RuntimeMetricsRecorder | None = None,
    timeout_seconds: float | None = None,
) -> StructuredModelProvider:
    retry = RetryPolicy(
        max_retries=settings.provider_max_retries,
        base_delay_ms=settings.provider_retry_base_delay_ms,
    )
    if settings.chat_model_provider == "anthropic":
        return AnthropicStructuredModelProvider(
            model=settings.chat_model_name,
            client_provider=partial(get_anthropic_client, settings),
            retry_policy=retry,
            timeout_seconds=timeout_seconds or settings.model_timeout_seconds,
            metrics=metrics,
        )
    return OpenAIStructuredModelProvider(
        model=settings.chat_model_name,
        store_responses=settings.openai_store_responses,
        client_provider=partial(get_openai_client, settings),
        retry_policy=retry,
        timeout_seconds=timeout_seconds or settings.model_timeout_seconds,
        metrics=metrics,
    )


def build_embedding_provider(
    settings: Settings,
    *,
    metrics: RuntimeMetricsRecorder | None = None,
) -> EmbeddingProvider:
    if settings.embedding_provider != "openai":
        raise ValueError("The configured embedding provider does not support embeddings")
    return OpenAIEmbeddingProvider(
        model=settings.embedding_model,
        dimension=settings.openai_embedding_dimension,
        client_provider=partial(get_openai_client, settings),
        retry_policy=RetryPolicy(
            max_retries=settings.provider_max_retries,
            base_delay_ms=settings.provider_retry_base_delay_ms,
        ),
        timeout_seconds=settings.embedding_timeout_seconds,
        metrics=metrics,
    )


def close_provider_clients() -> None:
    from app.providers.anthropic import close_anthropic_client
    from app.providers.openai import close_openai_client

    close_openai_client()
    close_anthropic_client()
