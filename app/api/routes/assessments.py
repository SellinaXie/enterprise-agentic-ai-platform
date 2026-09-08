"""Assessment API endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_assessment_service
from app.schemas.assessment import AssessmentRequest, AssessmentResponse
from app.schemas.errors import ErrorResponse
from app.services.assessments import AssessmentService

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post(
    "",
    response_model=AssessmentResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Generate an enterprise AI assessment",
)
def create_assessment(
    request: AssessmentRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
) -> AssessmentResponse:
    """Validate business context and synchronously generate a structured assessment."""
    return service.generate_assessment(request)
