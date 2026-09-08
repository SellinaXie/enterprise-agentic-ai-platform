"""Assessment application service."""

import logging
from typing import Protocol
from uuid import uuid4

from app.core.exceptions import ApplicationError
from app.models.assessment import AssessmentStatus
from app.schemas.assessment import AssessmentRequest, AssessmentResponse, AssessmentResult
from app.services.assessment_prompt import AssessmentPrompt, build_assessment_prompt

logger = logging.getLogger(__name__)


class AssessmentGenerator(Protocol):
    """Provider-independent interface for structured assessment generation."""

    def generate(self, prompt: AssessmentPrompt) -> AssessmentResult:
        """Generate a validated assessment result."""
        ...


class AssessmentService:
    """Coordinate assessment use cases independently of HTTP transport."""

    def __init__(self, generator: AssessmentGenerator) -> None:
        self._generator = generator

    def generate_assessment(self, request: AssessmentRequest) -> AssessmentResponse:
        """Build context, generate a validated result, and return it with an ID."""
        assessment_id = uuid4()
        log_context = {"assessment_id": str(assessment_id)}
        logger.info("assessment_request_received", extra=log_context)
        logger.info("assessment_generation_started", extra=log_context)

        try:
            result = self._generator.generate(build_assessment_prompt(request))
            response = AssessmentResponse(
                assessment_id=assessment_id,
                status=AssessmentStatus.COMPLETED,
                result=result,
            )
        except ApplicationError as exc:
            logger.warning(
                "assessment_failed",
                extra={**log_context, "error_code": exc.error_code},
            )
            raise

        logger.info("assessment_completed", extra=log_context)
        return response
