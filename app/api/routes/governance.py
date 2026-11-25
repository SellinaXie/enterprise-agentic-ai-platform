"""Read-only governance policy endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import current_policy_description
from app.core.config import Settings, get_settings
from app.identity.dependencies import get_authenticated_principal
from app.identity.models import AuthenticatedPrincipal
from app.schemas.errors import ErrorResponse
from app.schemas.product import GovernancePolicyResponse

router = APIRouter(
    prefix="/governance",
    tags=["governance"],
    dependencies=[Depends(get_authenticated_principal)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
    },
)


@router.get(
    "/policy",
    response_model=GovernancePolicyResponse,
    summary="Return the runtime risk policy and review rules in force",
)
def get_governance_policy(
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> GovernancePolicyResponse:
    """Read-only; values come from server configuration, never from the caller."""
    return current_policy_description(settings)
