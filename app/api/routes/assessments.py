"""Assessment API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_assessment_service, get_runtime_governance_service
from app.identity.dependencies import get_authenticated_principal, require_reviewer_or_admin
from app.identity.models import AuthenticatedPrincipal
from app.runtime.models import (
    HumanReviewDecision,
    HumanReviewRecord,
    HumanReviewRequest,
    RuntimeStatusResponse,
)
from app.schemas.assessment import AssessmentRequest, AssessmentResponse
from app.schemas.errors import ErrorResponse
from app.services.assessments import AssessmentService
from app.services.runtime_governance import RuntimeGovernanceService

router = APIRouter(
    prefix="/assessments",
    tags=["assessments"],
    dependencies=[Depends(get_authenticated_principal)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)


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
    principal: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> AssessmentResponse:
    """Validate business context and synchronously generate a structured assessment."""
    return service.generate_assessment(request, principal=principal)


@router.get(
    "/{assessment_id}",
    response_model=AssessmentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Retrieve a persisted enterprise AI assessment",
)
def get_assessment(
    assessment_id: UUID,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> AssessmentResponse:
    """Return persisted input, result or failure, and lifecycle timestamps."""
    return service.get_assessment(assessment_id)


@router.get(
    "/{assessment_id}/runtime-status",
    response_model=RuntimeStatusResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Retrieve runtime governance status and safe telemetry",
)
def get_runtime_status(
    assessment_id: UUID,
    service: Annotated[RuntimeGovernanceService, Depends(get_runtime_governance_service)],
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> RuntimeStatusResponse:
    return service.get_runtime_status(assessment_id)


@router.get(
    "/{assessment_id}/reviews",
    response_model=list[HumanReviewRecord],
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    summary="List immutable-style human review events",
)
def list_reviews(
    assessment_id: UUID,
    service: Annotated[RuntimeGovernanceService, Depends(get_runtime_governance_service)],
    _: Annotated[AuthenticatedPrincipal, Depends(require_reviewer_or_admin)],
) -> list[HumanReviewRecord]:
    return service.list_reviews(assessment_id)


@router.post(
    "/{assessment_id}/reviews/approve",
    response_model=HumanReviewDecision,
    responses={status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
    summary="Approve a pending assessment",
)
def approve_review(
    assessment_id: UUID,
    request: HumanReviewRequest,
    service: Annotated[RuntimeGovernanceService, Depends(get_runtime_governance_service)],
    principal: Annotated[AuthenticatedPrincipal, Depends(require_reviewer_or_admin)],
) -> HumanReviewDecision:
    return service.approve(assessment_id, request, principal=principal)


@router.post(
    "/{assessment_id}/reviews/reject",
    response_model=HumanReviewDecision,
    responses={status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
    summary="Reject a pending assessment",
)
def reject_review(
    assessment_id: UUID,
    request: HumanReviewRequest,
    service: Annotated[RuntimeGovernanceService, Depends(get_runtime_governance_service)],
    principal: Annotated[AuthenticatedPrincipal, Depends(require_reviewer_or_admin)],
) -> HumanReviewDecision:
    return service.reject(assessment_id, request, principal=principal)


@router.post(
    "/{assessment_id}/reviews/request-revision",
    response_model=HumanReviewDecision,
    responses={status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
    summary="Request a bounded assessment revision",
)
def request_review_revision(
    assessment_id: UUID,
    request: HumanReviewRequest,
    service: Annotated[RuntimeGovernanceService, Depends(get_runtime_governance_service)],
    principal: Annotated[AuthenticatedPrincipal, Depends(require_reviewer_or_admin)],
) -> HumanReviewDecision:
    return service.request_revision(assessment_id, request, principal=principal)
