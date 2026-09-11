"""Local JWT verification behind an OIDC-compatible verifier contract."""

from typing import Any, Protocol

import jwt
from jwt import InvalidTokenError

from app.core.exceptions import AuthenticationRequiredError
from app.identity.models import AuthenticatedPrincipal, Role


class TokenVerifier(Protocol):
    """Boundary that can later be implemented by an external OIDC/JWKS verifier."""

    def verify(self, token: str) -> AuthenticatedPrincipal: ...


class LocalJWTVerifier:
    """Verify signed JWTs with a fixed algorithm, issuer, audience, expiry, and subject."""

    def __init__(
        self,
        *,
        verification_key: str,
        algorithm: str,
        issuer: str,
        audience: str,
        leeway_seconds: int = 0,
    ) -> None:
        self._verification_key = verification_key
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience
        self._leeway_seconds = leeway_seconds

    def verify(self, token: str) -> AuthenticatedPrincipal:
        try:
            claims = jwt.decode(
                token,
                self._verification_key,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway_seconds,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
            return self._principal_from_claims(claims)
        except (InvalidTokenError, TypeError, ValueError, KeyError):
            raise AuthenticationRequiredError from None

    def _principal_from_claims(self, claims: dict[str, Any]) -> AuthenticatedPrincipal:
        subject = claims.get("sub")
        issuer = claims.get("iss")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationRequiredError
        if not isinstance(issuer, str) or not issuer.strip():
            raise AuthenticationRequiredError

        raw_roles = claims.get("roles", claims.get("role", []))
        if isinstance(raw_roles, str):
            raw_roles = [raw_roles]
        if not isinstance(raw_roles, list) or not raw_roles:
            raise AuthenticationRequiredError
        try:
            roles = frozenset(Role(str(value).casefold()) for value in raw_roles)
        except ValueError:
            raise AuthenticationRequiredError from None

        email = claims.get("email")
        display_name = claims.get("name", claims.get("display_name"))
        if email is not None and not isinstance(email, str):
            raise AuthenticationRequiredError
        if display_name is not None and not isinstance(display_name, str):
            raise AuthenticationRequiredError
        return AuthenticatedPrincipal(
            subject=subject,
            email=email,
            display_name=display_name,
            roles=roles,
            issuer=issuer,
        )
