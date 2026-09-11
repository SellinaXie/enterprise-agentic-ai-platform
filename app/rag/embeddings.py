"""Embedding contract and backward-compatible OpenAI adapter exports."""

from app.providers.contracts import EmbeddingProvider as EmbeddingsService
from app.providers.openai import OpenAIEmbeddingProvider as OpenAIEmbeddingsService

__all__ = ["EmbeddingsService", "OpenAIEmbeddingsService"]
