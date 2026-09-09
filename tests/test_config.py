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
    assert settings.agentic_workflow_enabled is False
    assert settings.agent_max_steps == 5
    assert settings.agent_max_tool_calls == 5
    assert settings.langgraph_recursion_limit == 25
    assert settings.multi_agent_workflow_enabled is False
    assert settings.evidence_agent_max_steps == 4
    assert settings.evidence_agent_max_tool_calls == 4
    assert settings.multi_agent_max_failures == 2
    assert settings.specialist_retry_limit == 1


def test_chunk_overlap_must_be_smaller_than_chunk_size() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, RAG_CHUNK_SIZE=300, RAG_CHUNK_OVERLAP=300)


def test_agentic_recursion_limit_must_cover_bounded_graph_path() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            AGENTIC_WORKFLOW_ENABLED=True,
            AGENT_MAX_STEPS=5,
            LANGGRAPH_RECURSION_LIMIT=12,
        )
