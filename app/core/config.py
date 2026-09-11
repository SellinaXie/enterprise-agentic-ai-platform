"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
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

    app_name: str = "Enterprise AI Architecture & Risk Intelligence Platform"
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
    openai_store_responses: bool = False

    rag_enabled: bool = False
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimension: Literal[1536] = KNOWLEDGE_EMBEDDING_DIMENSION
    rag_chunk_size: int = Field(default=1_200, ge=200, le=20_000)
    rag_chunk_overlap: int = Field(default=200, ge=0, le=5_000)
    rag_retrieval_top_k: int = Field(default=5, ge=1, le=20)
    rag_similarity_threshold: float = Field(default=0.35, ge=-1.0, le=1.0)

    knowledge_graph_enabled: bool = False
    graph_max_depth: int = Field(default=2, ge=1, le=5)
    graph_max_entities: int = Field(default=20, ge=1, le=100)
    graph_min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    max_upload_size_mb: int = Field(default=10, ge=1, le=100)
    pdf_min_extracted_characters: int = Field(default=100, ge=1, le=10_000)

    agentic_workflow_enabled: bool = False
    agent_max_steps: int = Field(default=5, ge=1, le=50)
    agent_max_tool_calls: int = Field(default=5, ge=1, le=50)
    langgraph_recursion_limit: int = Field(default=25, ge=1, le=1_000)

    multi_agent_workflow_enabled: bool = False
    evidence_agent_max_steps: int = Field(default=4, ge=1, le=50)
    evidence_agent_max_tool_calls: int = Field(default=4, ge=1, le=50)
    multi_agent_max_failures: int = Field(default=2, ge=0, le=2)
    specialist_retry_limit: int = Field(default=1, ge=0, le=3)

    runtime_risk_gate_enabled: bool = False
    runtime_medium_risk_decision: Literal[
        "auto_complete", "complete_with_warning", "require_human_review", "block_and_escalate"
    ] = "complete_with_warning"
    runtime_high_risk_decision: Literal[
        "auto_complete", "complete_with_warning", "require_human_review", "block_and_escalate"
    ] = "require_human_review"
    runtime_critical_risk_decision: Literal[
        "auto_complete", "complete_with_warning", "require_human_review", "block_and_escalate"
    ] = "block_and_escalate"
    runtime_review_on_insufficient_evidence: bool = True
    runtime_review_on_degraded_execution: bool = True
    runtime_review_on_specialist_unavailable: bool = True
    runtime_review_on_tool_failure: bool = True
    runtime_block_high_risk_invalid_provenance: bool = True
    runtime_block_critical_missing_mitigation: bool = True
    max_human_revisions: int = Field(default=2, ge=0, le=10)

    provider_max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        validation_alias=AliasChoices("PROVIDER_MAX_RETRIES", "OPENAI_MAX_RETRIES"),
    )
    provider_retry_base_delay_ms: int = Field(default=250, ge=0, le=60_000)
    model_timeout_seconds: float = Field(default=30.0, gt=0)
    embedding_timeout_seconds: float = Field(default=30.0, gt=0)
    tool_timeout_seconds: float = Field(default=10.0, gt=0)
    graph_extraction_timeout_seconds: float = Field(default=30.0, gt=0)
    model_input_cost_per_1m_tokens: float | None = Field(default=None, ge=0)
    model_output_cost_per_1m_tokens: float | None = Field(default=None, ge=0)

    evaluation_llm_judge_enabled: bool = False
    evaluation_judge_model: str = "gpt-4.1-mini"

    @property
    def openai_max_retries(self) -> int:
        """Backward-compatible name for the centralized provider retry limit."""
        return self.provider_max_retries

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
