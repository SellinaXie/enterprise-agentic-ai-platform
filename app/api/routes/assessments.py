"""Assessment API endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_assessment_service, get_runtime_governance_service
from app.core.config import Settings, get_settings
from app.core.exceptions import ExecutionModeSelectionDisabledError
from app.identity.dependencies import get_authenticated_principal, require_reviewer_or_admin
from app.identity.models import AuthenticatedPrincipal
from app.runtime.models import (
    HumanReviewDecision,
    HumanReviewRecord,
    HumanReviewRequest,
    RuntimeStatusResponse,
)
from app.schemas.assessment import AssessmentRequest, AssessmentResponse
from app.schemas.decision_record import DecisionRecordResponse
from app.schemas.errors import ErrorResponse
from app.schemas.product import (
    CandidateVersionsResponse,
    ReviewCandidateResponse,
    RevisionSubmissionResponse,
)
from app.services.assessments import AssessmentService
from app.services.execution_router import ExecutionMode
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
    settings: Annotated[Settings, Depends(get_settings)],
    execution_mode: Annotated[
        ExecutionMode | None,
        Query(
            description=(
                "Demo deployments only (EXECUTION_MODE_SELECTION_ENABLED=true): run this "
                "request in the given mode. Rejected with 403 elsewhere."
            ),
        ),
    ] = None,
) -> AssessmentResponse:
    """Validate business context and synchronously generate a structured assessment."""
    if execution_mode is None:
        return service.generate_assessment(request, principal=principal)
    if not settings.execution_mode_selection_enabled:
        raise ExecutionModeSelectionDisabledError
    return service.generate_assessment(
        request, principal=principal, requested_execution_mode=execution_mode
    )


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


@router.get(
    "/{assessment_id}/review-candidate",
    response_model=ReviewCandidateResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    summary="Retrieve the persisted candidate for authenticated human review",
)
def get_review_candidate(
    assessment_id: UUID,
    service: Annotated[RuntimeGovernanceService, Depends(get_runtime_governance_service)],
    principal: Annotated[AuthenticatedPrincipal, Depends(require_reviewer_or_admin)],
) -> ReviewCandidateResponse:
    """Return the candidate plus the review actions this caller may take now."""
    return service.get_review_candidate(assessment_id, principal=principal)


@router.get(
    "/{assessment_id}/candidate-versions",
    response_model=CandidateVersionsResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    summary="List every gated candidate version for comparison",
)
def list_candidate_versions(
    assessment_id: UUID,
    service: Annotated[RuntimeGovernanceService, Depends(get_runtime_governance_service)],
    _: Annotated[AuthenticatedPrincipal, Depends(require_reviewer_or_admin)],
) -> CandidateVersionsResponse:
    """Return candidates oldest first; version 0 is the original."""
    return service.list_candidate_versions(assessment_id)


@router.post(
    "/{assessment_id}/revisions",
    response_model=RevisionSubmissionResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_502_BAD_GATEWAY: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
    summary="Regenerate the candidate from the latest reviewer feedback",
)
def submit_revision(
    assessment_id: UUID,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    principal: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> RevisionSubmissionResponse:
    """Allowed for the assessment's creator, reviewers and admins; the body is empty."""
    return service.submit_revision(assessment_id, principal=principal)


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


@router.get(
    "/{assessment_id}/decision-record",
    response_model=DecisionRecordResponse,
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
    summary="Export the decision record: input, routing, evidence, versions, reviews, outcome",
)
def get_decision_record(
    assessment_id: UUID,
    service: Annotated[RuntimeGovernanceService, Depends(get_runtime_governance_service)],
    _: Annotated[AuthenticatedPrincipal, Depends(require_reviewer_or_admin)],
) -> DecisionRecordResponse:
    """Built only from persisted state; the fingerprint is stable while the state is unchanged."""
    return service.build_decision_record(assessment_id)
