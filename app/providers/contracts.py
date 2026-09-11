"""Narrow contracts consumed by application workflows, independent of vendor SDKs."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class ProviderName(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    structured_output: bool
    tool_calling: bool
    usage_reporting: bool
    embeddings: bool


@dataclass(frozen=True, slots=True)
class ToolCallDecision:
    name: str
    arguments: dict[str, Any]


class ProviderError(Exception):
    """Safe vendor-neutral provider failure used by retry classification."""


class ProviderTransientError(ProviderError):
    pass


class ProviderTimeoutError(ProviderError):
    pass


class ProviderPermanentError(ProviderError):
    pass


class StructuredModelProvider(Protocol):
    """Only the structured generation and bounded tool-decision operations we use."""

    @property
    def name(self) -> ProviderName: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def generate_structured(
        self,
        *,
        system: str,
        user: str,
        output_model: type[StructuredModel],
    ) -> StructuredModel: ...

    def decide_tool_call(
        self,
        *,
        system: str,
        user: str,
        tools: list[dict[str, Any]],
        max_output_tokens: int = 200,
    ) -> ToolCallDecision | None: ...


class EmbeddingProvider(Protocol):
    """Only the ordered batch embedding operation required by RAG."""

    @property
    def name(self) -> ProviderName: ...

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
