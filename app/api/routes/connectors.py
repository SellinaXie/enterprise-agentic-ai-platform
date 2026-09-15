"""Admin-only enterprise connector operations."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_policy_repository_connector
from app.connectors.policy_repository import PolicyRepositoryConnector
from app.identity.dependencies import require_admin
from app.schemas.connectors import PolicyRepositorySyncRequest, PolicyRepositorySyncResponse
from app.schemas.errors import ErrorResponse

router = APIRouter(
    prefix="/connectors",
    tags=["connectors"],
    dependencies=[Depends(require_admin)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
    },
)


@router.post(
    "/policy-repository/sync",
    response_model=PolicyRepositorySyncResponse,
    summary="Pull policies from the configured read-only repository",
)
def sync_policy_repository(
    request: PolicyRepositorySyncRequest,
    connector: Annotated[PolicyRepositoryConnector, Depends(get_policy_repository_connector)],
) -> PolicyRepositorySyncResponse:
    return PolicyRepositorySyncResponse.model_validate(
        connector.sync(enrich_graph=request.enrich_graph)
    )
