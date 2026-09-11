"""Mocked provider contracts, capabilities, and built-in selection tests."""

from types import SimpleNamespace
from unittest.mock import Mock

from pydantic import BaseModel

from app.core.config import Settings
from app.providers.anthropic import AnthropicStructuredModelProvider
from app.providers.contracts import ProviderName
from app.providers.factory import build_embedding_provider, build_structured_model_provider
from app.providers.openai import OpenAIEmbeddingProvider, OpenAIStructuredModelProvider


class SyntheticOutput(BaseModel):
    answer: str


def test_openai_and_anthropic_publish_explicit_capabilities() -> None:
    assert OpenAIStructuredModelProvider.capabilities.structured_output is True
    assert OpenAIStructuredModelProvider.capabilities.tool_calling is True
    assert OpenAIStructuredModelProvider.capabilities.embeddings is True
    assert AnthropicStructuredModelProvider.capabilities.structured_output is True
    assert AnthropicStructuredModelProvider.capabilities.tool_calling is True
    assert AnthropicStructuredModelProvider.capabilities.embeddings is False


def test_anthropic_structured_output_uses_schema_constrained_tool() -> None:
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="submit_structured_result",
                input={"answer": "grounded"},
            )
        ],
        usage=SimpleNamespace(input_tokens=10, output_tokens=4),
    )
    client = Mock()
    client.messages.create.return_value = response
    provider = AnthropicStructuredModelProvider(
        model="claude-test",
        client_provider=lambda: client,
    )

    result = provider.generate_structured(
        system="Return a typed result.",
        user="Synthetic fixture only.",
        output_model=SyntheticOutput,
    )

    assert result == SyntheticOutput(answer="grounded")
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "tool", "name": "submit_structured_result"}
    assert kwargs["tools"][0]["input_schema"]["properties"]["answer"]["type"] == "string"


def test_anthropic_maps_existing_tool_schema_without_vendor_leakage() -> None:
    client = Mock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name="search", input={"query": "controls"})]
    )
    provider = AnthropicStructuredModelProvider(
        model="claude-test",
        client_provider=lambda: client,
    )

    decision = provider.decide_tool_call(
        system="Use tools only when needed.",
        user="Find controls.",
        tools=[
            {
                "type": "function",
                "name": "search",
                "description": "Search synthetic knowledge.",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            }
        ],
    )

    assert decision is not None
    assert decision.name == "search"
    assert decision.arguments == {"query": "controls"}
    assert client.messages.create.call_args.kwargs["tools"][0]["input_schema"]["type"] == "object"


def test_factory_selects_chat_and_embedding_providers_independently() -> None:
    settings = Settings(
        _env_file=None,
        CHAT_MODEL_PROVIDER="anthropic",
        CHAT_MODEL_NAME="claude-test",
        ANTHROPIC_API_KEY="synthetic-anthropic-value",
        EMBEDDING_PROVIDER="openai",
        EMBEDDING_MODEL="embedding-test",
        OPENAI_API_KEY="synthetic-openai-value",
    )

    structured = build_structured_model_provider(settings)
    embeddings = build_embedding_provider(settings)

    assert structured.name == ProviderName.ANTHROPIC
    assert embeddings.name == ProviderName.OPENAI
    assert isinstance(embeddings, OpenAIEmbeddingProvider)
