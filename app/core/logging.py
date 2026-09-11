"""Structured JSON logging configuration."""

import json
import logging
from datetime import UTC, datetime
from logging.config import dictConfig
from typing import Any

from app.core.context import get_request_id


class JsonFormatter(logging.Formatter):
    """Format standard log records as single-line JSON objects."""

    _reserved_fields = frozenset(logging.makeLogRecord({}).__dict__)
    _sensitive_fields = frozenset(
        {
            "authorization",
            "authorization_header",
            "api_key",
            "database_url",
            "document",
            "document_content",
            "embedding",
            "embeddings",
            "password",
            "claims",
            "prompt",
            "provider_message",
            "reasoning",
            "secret",
            "token",
            "jwt",
            "system_prompt",
            "tool_arguments",
            "user_prompt",
        }
    )

    def __init__(self, *, include_exception_tracebacks: bool = False) -> None:
        super().__init__()
        self._include_exception_tracebacks = include_exception_tracebacks

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        payload.update(
            {
                key: value
                for key, value in record.__dict__.items()
                if key not in self._reserved_fields
                and key not in {"message", "asctime", "request_id"}
                and key.casefold() not in self._sensitive_fields
                and not key.casefold().endswith(
                    ("_password", "_secret", "_api_key", "_token", "_jwt", "_claims")
                )
            }
        )
        if record.exc_info:
            exception_type = record.exc_info[0]
            payload["exception_type"] = (
                exception_type.__name__ if exception_type is not None else "Exception"
            )
            if self._include_exception_tracebacks:
                payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    log_level: str = "INFO", *, include_exception_tracebacks: bool = False
) -> None:
    """Configure application and server logs for machine-readable output."""
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": JsonFormatter,
                    "include_exception_tracebacks": include_exception_tracebacks,
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                }
            },
            "root": {"handlers": ["default"], "level": log_level},
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": log_level, "propagate": False},
                "uvicorn.access": {
                    "handlers": ["default"],
                    "level": log_level,
                    "propagate": False,
                },
            },
        }
    )
