"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = Field(default=30.0, gt=0)
    openai_max_retries: int = Field(default=2, ge=0, le=10)
    openai_store_responses: bool = False

    langgraph_recursion_limit: int = Field(default=25, ge=1, le=1_000)


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance for the current process."""
    return Settings()
