"""Health endpoint schemas."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Service liveness response."""

    status: Literal["ok"]
    version: str
