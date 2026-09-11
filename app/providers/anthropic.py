"""Anthropic structured reasoning adapter; embeddings are intentionally unsupported."""

from collections.abc import Callable
from functools import lru_cache
from time import perf_counter, sleep
from typing import Any

from anthropic import (
    Anthropic,
    AnthropicError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from app.core.config import Settings, get_settings
from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    ModelProviderNotConfiguredError,
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

ANTHROPIC_CAPABILITIES = ProviderCapabilities(
    structured_output=True,
    tool_calling=True,
    usage_reporting=True,
    embeddings=False,
)


def create_anthropic_client(settings: Settings) -> Anthropic:
    if (
        settings.anthropic_api_key is None
        or not settings.anthropic_api_key.get_secret_value().strip()
    ):
        raise ModelProviderNotConfiguredError
    return Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.model_timeout_seconds,
        max_retries=0,
    )


@lru_cache
def _get_default_anthropic_client() -> Anthropic:
    return create_anthropic_client(get_settings())


def get_anthropic_client(settings: Settings | None = None) -> Anthropic:
    return (
        create_anthropic_client(settings)
        if settings is not None
        else _get_default_anthropic_client()
    )


def close_anthropic_client() -> None:
    if _get_default_anthropic_client.cache_info().currsize:
        _get_default_anthropic_client().close()
    _get_default_anthropic_client.cache_clear()


def _normalize_error(exc: Exception) -> Exception:
    if isinstance(exc, APITimeoutError):
        return ProviderTimeoutError()
    if isinstance(exc, RateLimitError | APIConnectionError | InternalServerError):
        return ProviderTransientError()
    if isinstance(exc, AnthropicError):
        return ProviderPermanentError()
    return exc


class AnthropicStructuredModelProvider:
    """Use forced tool output as a schema-constrained JSON transport."""

    name = ProviderName.ANTHROPIC
    capabilities = ANTHROPIC_CAPABILITIES

    def __init__(
        self,
        *,
        model: str,
        client_provider: Callable[[], Any] = get_anthropic_client,
        retry_policy: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
        metrics: RuntimeMetricsRecorder | None = None,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._model = model
        self._client_provider = client_provider
        self._retry_policy = retry_policy
        self._timeout_seconds = timeout_seconds
        self._metrics = metrics
        self._sleeper = sleeper

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        output_model: type[StructuredModel],
    ) -> StructuredModel:
        tool_name = "submit_structured_result"
        response = self._create(
            system=system,
            user=user,
            tools=[
                {
                    "name": tool_name,
                    "description": "Submit the complete validated structured result.",
                    "input_schema": output_model.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
            max_tokens=4096,
        )
        block = next(
            (
                item
                for item in getattr(response, "content", ())
                if getattr(item, "type", None) == "tool_use"
                and getattr(item, "name", None) == tool_name
            ),
            None,
        )
        if block is None:
            raise InvalidLLMResponseError
        try:
            return output_model.model_validate(block.input)
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
        anthropic_tools = [
            {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "input_schema": tool["parameters"],
            }
            for tool in tools
        ]
        response = self._create(
            system=system,
            user=user,
            tools=anthropic_tools,
            tool_choice={"type": "auto"},
            max_tokens=max_output_tokens,
        )
        block = next(
            (
                item
                for item in getattr(response, "content", ())
                if getattr(item, "type", None) == "tool_use"
            ),
            None,
        )
        if block is None:
            return None
        arguments = block.input if isinstance(block.input, dict) else {}
        return ToolCallDecision(name=str(block.name), arguments=arguments)

    def _create(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        tool_choice: dict[str, str],
        max_tokens: int,
    ) -> Any:
        def request() -> Any:
            started = perf_counter()
            response = None
            request_kwargs: dict[str, Any] = {
                "model": self._model,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "tools": tools,
                "tool_choice": tool_choice,
                "max_tokens": max_tokens,
            }
            if self._timeout_seconds is not None:
                request_kwargs["timeout"] = self._timeout_seconds
            try:
                response = self._client_provider().messages.create(**request_kwargs)
                return response
            except Exception as exc:
                raise _normalize_error(exc) from exc
            finally:
                if self._metrics is not None:
                    self._metrics.record_model_call(
                        max(0, round((perf_counter() - started) * 1_000)), response
                    )

        try:
            return (
                run_with_retry(
                    request,
                    policy=self._retry_policy,
                    sleeper=self._sleeper,
                    on_retry=(self._metrics.record_retry if self._metrics else None),
                )
                if self._retry_policy is not None
                else request()
            )
        except (ProviderTimeoutError, ProviderTransientError, ProviderPermanentError) as exc:
            raise LLMProviderError from exc
        except (TypeError, ValueError) as exc:
            raise InvalidLLMResponseError from exc
