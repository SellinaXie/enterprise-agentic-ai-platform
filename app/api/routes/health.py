"""Liveness endpoint."""

from fastapi import APIRouter

from app import __version__
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Check service health")
def health_check() -> HealthResponse:
    """Return a lightweight liveness response."""
    return HealthResponse(status="ok", version=__version__)
