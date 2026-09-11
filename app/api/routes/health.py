"""Deployment liveness and dependency readiness endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app import __version__
from app.core.config import Settings, get_settings
from app.db.session import get_database_url, get_engine
from app.schemas.health import HealthResponse, ReadinessChecks, ReadinessResponse

router = APIRouter(tags=["health"])
ALEMBIC_HEAD_REVISION = "20260911_0006"
REQUIRED_TABLES = frozenset(
    {
        "assessments",
        "knowledge_documents",
        "knowledge_chunks",
        "knowledge_entities",
        "knowledge_entity_mentions",
        "knowledge_relationships",
        "assessment_runtime_states",
        "human_review_events",
    }
)


@router.get("/health", response_model=HealthResponse, summary="Check service health")
def health_check() -> HealthResponse:
    """Return a lightweight liveness response."""
    return HealthResponse(status="ok", version=__version__)


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
    summary="Check traffic readiness",
)
def readiness_check(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse:
    """Check configuration, database connectivity, and the expected schema revision."""
    configuration_ready = not settings.provider_required or settings.provider_is_configured
    database_ready = False
    schema_ready = False

    try:
        database_url = get_database_url(settings)
        engine = get_engine(database_url, settings.database_connect_timeout_seconds)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1")).scalar_one()
            database_ready = True
            table_names = set(inspect(connection).get_table_names())
            if "alembic_version" in table_names:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one_or_none()
                schema_ready = revision == ALEMBIC_HEAD_REVISION and table_names >= REQUIRED_TABLES
    except (SQLAlchemyError, ValueError):
        database_ready = False
        schema_ready = False
    except Exception:
        # Readiness is deliberately failure-safe and never returns connection diagnostics.
        database_ready = False
        schema_ready = False

    ready = configuration_ready and database_ready and schema_ready
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if ready else "not_ready",
        checks=ReadinessChecks(
            database="ready" if database_ready else "not_ready",
            schema="ready" if schema_ready else "not_ready",
            configuration="ready" if configuration_ready else "not_ready",
        ),
    )
