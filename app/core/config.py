"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

KNOWLEDGE_EMBEDDING_DIMENSION = 1536
UNSAFE_PLACEHOLDER_MARKERS = ("change-me", "changeme", "placeholder", "replace-with")


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
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    cors_allow_credentials: bool = False
    trusted_hosts: str = "localhost,127.0.0.1,testserver"
    max_json_request_size_kb: int = Field(default=256, ge=1, le=10_240)
    request_id_max_length: int = Field(default=64, ge=16, le=128)
    log_exception_tracebacks: bool = False

    database_url: SecretStr | None = Field(default=None, validation_alias="DATABASE_URL")
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=30)

    chat_model_provider: Literal["openai", "anthropic"] = "openai"
    chat_model_name: str = Field(
        default="gpt-4.1-mini",
        validation_alias=AliasChoices("CHAT_MODEL_NAME", "OPENAI_MODEL"),
    )
    embedding_provider: Literal["openai"] = "openai"
    embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "OPENAI_EMBEDDING_MODEL"),
    )
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    openai_store_responses: bool = False
    provider_required: bool = True

    rag_enabled: bool = False
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

    auth_enabled: bool = False
    auth_jwt_algorithm: Literal["HS256", "RS256"] = "HS256"
    auth_jwt_verification_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AUTH_JWT_VERIFICATION_KEY", "AUTH_JWT_SECRET", "AUTH_JWT_PUBLIC_KEY"
        ),
    )
    auth_jwt_issuer: str | None = None
    auth_jwt_audience: str | None = None
    auth_jwt_leeway_seconds: int = Field(default=30, ge=0, le=300)

    @property
    def openai_model(self) -> str:
        """Backward-compatible alias for the configured chat model."""
        return self.chat_model_name

    @property
    def openai_embedding_model(self) -> str:
        """Backward-compatible alias for the configured embedding model."""
        return self.embedding_model

    @property
    def openai_max_retries(self) -> int:
        """Backward-compatible name for the centralized provider retry limit."""
        return self.provider_max_retries

    @property
    def parsed_cors_allowed_origins(self) -> list[str]:
        """Return the explicit configured CORS allowlist."""
        return [value.strip() for value in self.cors_allowed_origins.split(",") if value.strip()]

    @property
    def parsed_trusted_hosts(self) -> list[str]:
        """Return the explicit ASGI trusted-host allowlist."""
        return [value.strip() for value in self.trusted_hosts.split(",") if value.strip()]

    @property
    def provider_is_configured(self) -> bool:
        """Report provider configuration without exposing the credential."""
        credential = (
            self.anthropic_api_key
            if self.chat_model_provider == "anthropic"
            else self.openai_api_key
        )
        return bool(credential is not None and credential.get_secret_value().strip())

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
        if (self.model_input_cost_per_1m_tokens is None) != (
            self.model_output_cost_per_1m_tokens is None
        ):
            raise ValueError(
                "MODEL_INPUT_COST_PER_1M_TOKENS and MODEL_OUTPUT_COST_PER_1M_TOKENS "
                "must be configured together"
            )

        for origin in self.parsed_cors_allowed_origins:
            parsed = urlsplit(origin)
            if origin == "*":
                continue
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("CORS_ALLOWED_ORIGINS must contain valid HTTP(S) origins")

        if self.environment == "production":
            self._validate_production_settings()
        elif self.auth_enabled:
            self._validate_auth_settings()
        return self

    def _validate_auth_settings(self) -> None:
        if self.auth_jwt_verification_key is None:
            raise ValueError("AUTH_JWT_VERIFICATION_KEY is required when authentication is enabled")
        if not self.auth_jwt_issuer or not self.auth_jwt_audience:
            raise ValueError(
                "AUTH_JWT_ISSUER and AUTH_JWT_AUDIENCE are required when authentication is enabled"
            )

    def _validate_production_settings(self) -> None:
        """Reject silent development fallbacks at the production boundary."""
        if self.debug:
            raise ValueError("APP_DEBUG must be false in production")
        if self.log_exception_tracebacks:
            raise ValueError("LOG_EXCEPTION_TRACEBACKS must be false in production")
        if "*" in self.parsed_cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS cannot contain '*' in production")
        if self.cors_allow_credentials and not self.parsed_cors_allowed_origins:
            raise ValueError("CORS_ALLOWED_ORIGINS must be explicit when credentials are allowed")
        if not self.parsed_trusted_hosts or "*" in self.parsed_trusted_hosts:
            raise ValueError("TRUSTED_HOSTS must be an explicit allowlist in production")

        if self.database_url is None:
            raise ValueError("DATABASE_URL is required in production")
        database_url = self.database_url.get_secret_value().strip()
        if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must use PostgreSQL in production")
        if any(marker in database_url.casefold() for marker in UNSAFE_PLACEHOLDER_MARKERS):
            raise ValueError("DATABASE_URL contains an unsafe placeholder in production")

        provider_needed = self.provider_required or any(
            (
                self.rag_enabled,
                self.agentic_workflow_enabled,
                self.multi_agent_workflow_enabled,
                self.knowledge_graph_enabled,
                self.evaluation_llm_judge_enabled,
            )
        )
        if provider_needed and not self.provider_is_configured:
            credential_name = (
                "ANTHROPIC_API_KEY" if self.chat_model_provider == "anthropic" else "OPENAI_API_KEY"
            )
            raise ValueError(f"{credential_name} is required by the enabled production profile")
        if (self.rag_enabled or self.knowledge_graph_enabled) and (
            self.openai_api_key is None or not self.openai_api_key.get_secret_value().strip()
        ):
            raise ValueError("OPENAI_API_KEY is required for OpenAI embeddings")
        if self.provider_is_configured:
            selected_key = (
                self.anthropic_api_key
                if self.chat_model_provider == "anthropic"
                else self.openai_api_key
            )
            api_key = selected_key.get_secret_value().casefold()  # type: ignore[union-attr]
            if any(marker in api_key for marker in UNSAFE_PLACEHOLDER_MARKERS):
                raise ValueError("Selected provider API key contains an unsafe placeholder")

        if not self.auth_enabled:
            raise ValueError("AUTH_ENABLED must be true in production")
        self._validate_auth_settings()
        assert self.auth_jwt_verification_key is not None
        verification_key = self.auth_jwt_verification_key.get_secret_value().strip()
        if len(verification_key) < 32 or any(
            marker in verification_key.casefold() for marker in UNSAFE_PLACEHOLDER_MARKERS
        ):
            raise ValueError("AUTH_JWT_VERIFICATION_KEY is unsafe for production")


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance for the current process."""
    return Settings()
