"""Configuration secrecy and centralized RAG setting tests."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_database_url_is_redacted_from_settings_representation() -> None:
    settings = Settings(
        _env_file=None,
        DATABASE_URL="postgresql+psycopg://user:private-password@localhost/enterprise_ai",
    )

    assert "private-password" not in repr(settings)
    assert "**********" in repr(settings)


def test_rag_defaults_match_the_vector_schema() -> None:
    settings = Settings(_env_file=None)

    assert settings.openai_embedding_model == "text-embedding-3-small"
    assert settings.openai_embedding_dimension == 1536
    assert settings.rag_chunk_size == 1_200
    assert settings.rag_chunk_overlap == 200
    assert settings.rag_retrieval_top_k == 5
    assert settings.rag_similarity_threshold == 0.35


def test_chunk_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, RAG_CHUNK_SIZE=300, RAG_CHUNK_OVERLAP=300)
