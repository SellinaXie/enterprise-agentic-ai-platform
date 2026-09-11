"""Health endpoint schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Service liveness response."""

    status: Literal["ok"]
    version: str


class ReadinessChecks(BaseModel):
    """Non-sensitive dependency readiness states."""

    database: Literal["ready", "not_ready"]
    schema_status: Literal["ready", "not_ready"] = Field(alias="schema")
    configuration: Literal["ready", "not_ready"]


class ReadinessResponse(BaseModel):
    """Deployment readiness without credentials or internal exception details."""

    status: Literal["ready", "not_ready"]
    checks: ReadinessChecks
