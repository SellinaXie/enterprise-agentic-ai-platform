"""API dependency wiring for application services."""

from functools import partial
from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.assessments import AssessmentService
from app.services.llm import OpenAIAssessmentGenerator, get_openai_client


def get_assessment_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AssessmentService:
    """Build the V1 assessment service with a lazily created OpenAI client."""
    generator = OpenAIAssessmentGenerator(
        model=settings.openai_model,
        store_responses=settings.openai_store_responses,
        client_provider=partial(get_openai_client, settings),
    )
    return AssessmentService(generator)
