"""Read-only product endpoints for the V8C enterprise interface."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_product_read_service
from app.core.config import Settings, get_settings
from app.evaluation.assessment.dataset import load_assessment_dataset
from app.evaluation.assessment.models import AssessmentEvaluationMode
from app.evaluation.assessment.runner import build_fixture_runner
from app.evaluation.dataset import load_evaluation_dataset
from app.evaluation.models import EvaluationMode
from app.evaluation.runner import build_deterministic_runner
from app.identity.dependencies import get_authenticated_principal, require_reviewer_or_admin
from app.identity.models import AuthenticatedPrincipal
from app.models.assessment import AssessmentStatus
from app.schemas.errors import ErrorResponse
from app.schemas.product import (
    AssessmentListResponse,
    EvaluationModeSummary,
    EvaluationSummaryResponse,
    PrincipalResponse,
)
from app.services.product_read import ProductReadService

router = APIRouter(
    tags=["product"],
    dependencies=[Depends(get_authenticated_principal)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)


@router.get("/session", response_model=PrincipalResponse, summary="Return the current principal")
def get_session(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> PrincipalResponse:
    return PrincipalResponse(
        subject=principal.subject,
        email=principal.email,
        display_name=principal.display_name,
        roles=sorted(role.value for role in principal.roles),
        issuer=principal.issuer,
    )


@router.get(
    "/assessments",
    response_model=AssessmentListResponse,
    summary="List a bounded page of assessment summaries",
)
def list_assessments(
    service: Annotated[ProductReadService, Depends(get_product_read_service)],
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
    assessment_status: Annotated[AssessmentStatus | None, Query(alias="status")] = None,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AssessmentListResponse:
    return service.list_assessments(status=assessment_status, offset=offset, limit=limit)


@router.get(
    "/reviews/pending",
    response_model=AssessmentListResponse,
    summary="List assessments awaiting reviewer action",
)
def list_pending_reviews(
    service: Annotated[ProductReadService, Depends(get_product_read_service)],
    _: Annotated[AuthenticatedPrincipal, Depends(require_reviewer_or_admin)],
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> AssessmentListResponse:
    return service.list_assessments(
        status=AssessmentStatus.PENDING_REVIEW,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/evaluation/summary",
    response_model=EvaluationSummaryResponse,
    summary="Run the existing deterministic V7A and V7B aggregate evaluations",
)
def get_evaluation_summary(
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> EvaluationSummaryResponse:
    retrieval_dataset = load_evaluation_dataset()
    retrieval_runner = build_deterministic_runner(retrieval_dataset, settings)
    retrieval_reports = [retrieval_runner.run(mode) for mode in EvaluationMode]

    assessment_dataset = load_assessment_dataset()
    assessment_runner = build_fixture_runner(assessment_dataset, settings, enable_judge=False)
    assessment_reports = [assessment_runner.run(mode) for mode in AssessmentEvaluationMode]

    return EvaluationSummaryResponse(
        v7a=[
            EvaluationModeSummary(
                mode=report.evaluation_mode.value,
                synthetic=report.synthetic,
                total_cases=report.total_cases,
                evaluated_cases=report.evaluated_cases,
                aggregate_metrics=report.aggregate_metrics.model_dump(mode="json"),
                warnings=report.warnings,
            )
            for report in retrieval_reports
        ],
        v7b=[
            EvaluationModeSummary(
                mode=report.mode.value,
                synthetic=report.synthetic,
                total_cases=report.total_cases,
                evaluated_cases=report.evaluated_cases,
                aggregate_metrics=report.aggregate_metrics.model_dump(mode="json"),
                warnings=report.warnings,
                reproducibility_fingerprint=report.reproducibility_fingerprint,
            )
            for report in assessment_reports
        ],
        disclaimer=(
            "Synthetic deterministic benchmark results validate fixtures and contracts; "
            "they do not constitute production assurance or live-provider quality evidence."
        ),
    )
