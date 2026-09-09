"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KNOWLEDGE_EMBEDDING_DIMENSION = 1536


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Enterprise AI Transformation Advisor"
    environment: Literal["local", "development", "test", "staging", "production"] = Field(
        default="local",
        validation_alias="APP_ENV",
    )
    debug: bool = Field(default=False, validation_alias="APP_DEBUG")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        validation_alias="APP_LOG_LEVEL",
    )
    api_v1_prefix: str = "/api/v1"

    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    openai_max_retries: int = Field(default=2, ge=0, le=10)
    openai_store_responses: bool = False

    rag_enabled: bool = False
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimension: Literal[1536] = KNOWLEDGE_EMBEDDING_DIMENSION
    rag_chunk_size: int = Field(default=1_200, ge=200, le=20_000)
    rag_chunk_overlap: int = Field(default=200, ge=0, le=5_000)
    rag_retrieval_top_k: int = Field(default=5, ge=1, le=20)
    rag_similarity_threshold: float = Field(default=0.35, ge=-1.0, le=1.0)

    agentic_workflow_enabled: bool = False
    agent_max_steps: int = Field(default=5, ge=1, le=50)
    agent_max_tool_calls: int = Field(default=5, ge=1, le=50)
    langgraph_recursion_limit: int = Field(default=25, ge=1, le=1_000)

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> Self:
        """Require overlap to be smaller than the deterministic chunk size."""
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        minimum_recursion_limit = self.agent_max_steps * 2 + 3
        if self.agentic_workflow_enabled and (
            self.langgraph_recursion_limit < minimum_recursion_limit
        ):
            raise ValueError(
                "LANGGRAPH_RECURSION_LIMIT must be at least 2 * AGENT_MAX_STEPS + 3 "
                "when AGENTIC_WORKFLOW_ENABLED is true"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance for the current process."""
    return Settings()
