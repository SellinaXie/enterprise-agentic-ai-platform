"""FastAPI authentication and role dependencies."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationRequiredError, PermissionDeniedError
from app.identity.models import AuthenticatedPrincipal, Role
from app.identity.tokens import LocalJWTVerifier, TokenVerifier

bearer_scheme = HTTPBearer(auto_error=False)


def get_token_verifier(
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenVerifier | None:
    if not settings.auth_enabled:
        return None
    key = settings.auth_jwt_verification_key
    if key is None or settings.auth_jwt_issuer is None or settings.auth_jwt_audience is None:
        raise AuthenticationRequiredError
    return LocalJWTVerifier(
        verification_key=key.get_secret_value(),
        algorithm=settings.auth_jwt_algorithm,
        issuer=settings.auth_jwt_issuer,
        audience=settings.auth_jwt_audience,
        leeway_seconds=settings.auth_jwt_leeway_seconds,
    )


def get_authenticated_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    verifier: Annotated[TokenVerifier | None, Depends(get_token_verifier)],
) -> AuthenticatedPrincipal:
    if not settings.auth_enabled:
        return AuthenticatedPrincipal(
            subject="local-development",
            display_name="Local development principal",
            roles=frozenset({Role.ADMIN}),
            issuer="local-development",
        )
    if credentials is None or credentials.scheme.casefold() != "bearer" or verifier is None:
        raise AuthenticationRequiredError
    return verifier.verify(credentials.credentials)


def require_reviewer_or_admin(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> AuthenticatedPrincipal:
    if not principal.can_review():
        raise PermissionDeniedError
    return principal


def require_admin(
    principal: Annotated[AuthenticatedPrincipal, Depends(get_authenticated_principal)],
) -> AuthenticatedPrincipal:
    if Role.ADMIN not in principal.roles:
        raise PermissionDeniedError
    return principal
