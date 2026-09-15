"""Local JWT verification behind an OIDC-compatible verifier contract."""

from typing import Any, Protocol

import jwt
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError

from app.core.exceptions import AuthenticationRequiredError
from app.identity.models import AuthenticatedPrincipal, Role


class TokenVerifier(Protocol):
    """Boundary that can later be implemented by an external OIDC/JWKS verifier."""

    def verify(self, token: str) -> AuthenticatedPrincipal: ...


class SigningKey(Protocol):
    """Minimal PyJWT signing-key result used for network-free tests."""

    key: Any


class SigningKeyResolver(Protocol):
    """Resolve a JWT signing key by its untrusted header key id."""

    def get_signing_key_from_jwt(self, token: str) -> SigningKey: ...


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
            return principal_from_claims(claims)
        except (InvalidTokenError, TypeError, ValueError, KeyError):
            raise AuthenticationRequiredError from None


class OIDCJWKSVerifier:
    """Verify externally issued RS256 tokens using a cached JWKS resolver."""

    def __init__(
        self,
        *,
        jwks_url: str,
        issuer: str,
        audience: str,
        leeway_seconds: int = 0,
        cache_seconds: int = 300,
        timeout_seconds: int = 5,
        key_resolver: SigningKeyResolver | None = None,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._leeway_seconds = leeway_seconds
        self._key_resolver = key_resolver or PyJWKClient(
            jwks_url,
            cache_keys=True,
            lifespan=cache_seconds,
            timeout=timeout_seconds,
            headers={"User-Agent": "enterprise-agentic-ai-platform"},
        )

    def verify(self, token: str) -> AuthenticatedPrincipal:
        try:
            signing_key = self._key_resolver.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=self._leeway_seconds,
                options={"require": ["exp", "sub", "iss", "aud"]},
            )
            return principal_from_claims(claims)
        except (InvalidTokenError, PyJWKClientError, TypeError, ValueError, KeyError):
            raise AuthenticationRequiredError from None


def principal_from_claims(claims: dict[str, Any]) -> AuthenticatedPrincipal:
    """Map validated external identity claims into the existing RBAC principal."""
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
