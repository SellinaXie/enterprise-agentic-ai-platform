"""API dependency wiring for application services."""

from functools import partial
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.repositories.assessments import AssessmentRepository
from app.services.assessments import AssessmentGenerator, AssessmentService
from app.services.llm import OpenAIAssessmentGenerator, get_openai_client


def get_assessment_generator(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssessmentGenerator:
    """Build the structured generator with a lazily created OpenAI client."""
    return OpenAIAssessmentGenerator(
        model=settings.openai_model,
        store_responses=settings.openai_store_responses,
        client_provider=partial(get_openai_client, settings),
    )


def get_assessment_repository(
    session: Annotated[Session, Depends(get_db_session)],
) -> AssessmentRepository:
    """Build a repository around the request-scoped database session."""
    return AssessmentRepository(session)


def get_assessment_service(
    generator: Annotated[AssessmentGenerator, Depends(get_assessment_generator)],
    repository: Annotated[AssessmentRepository, Depends(get_assessment_repository)],
) -> AssessmentService:
    """Compose the service from provider and persistence boundaries."""
    return AssessmentService(generator, repository)
