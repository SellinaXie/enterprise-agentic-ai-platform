"""Shared OpenAI structured-output adapter for typed V5 specialist calls."""

from collections.abc import Callable
from typing import TypeVar

from openai import OpenAI, OpenAIError
from pydantic import BaseModel

from app.core.exceptions import (
    InvalidLLMResponseError,
    LLMProviderError,
    OpenAIClientNotConfiguredError,
)

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
    ) -> None:
        self._model = model
        self._store_responses = store_responses
        self._retry_limit = retry_limit
        self._client_provider = client_provider

    def generate(
        self,
        *,
        system: str,
        user: str,
        output_model: type[StructuredModel],
    ) -> StructuredModel:
        """Return a validated model or the existing safe provider/application error."""
        last_error: Exception | None = None
        for _ in range(self._retry_limit + 1):
            try:
                response = self._client_provider().responses.parse(
                    model=self._model,
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    text_format=output_model,
                    store=self._store_responses,
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise InvalidLLMResponseError
                return output_model.model_validate(parsed)
            except OpenAIClientNotConfiguredError:
                raise
            except OpenAIError as exc:
                last_error = LLMProviderError()
                last_error.__cause__ = exc
            except InvalidLLMResponseError as exc:
                last_error = exc
            except (TypeError, ValueError) as exc:
                last_error = InvalidLLMResponseError()
                last_error.__cause__ = exc

        if last_error is None:
            raise InvalidLLMResponseError
        raise last_error
