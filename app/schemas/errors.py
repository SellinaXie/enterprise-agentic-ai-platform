"""Stable API error response schemas."""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Machine-readable error code and safe user-facing message."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Envelope for controlled application errors."""

    error: ErrorDetail
