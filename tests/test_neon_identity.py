"""Neon signatures establish identity; workspace roles stay server controlled."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import Settings
from app.core.exceptions import AuthenticationRequiredError
from app.identity.models import Role
from app.identity.tokens import OIDCJWKSVerifier

KEY = Ed25519PrivateKey.generate()
ISSUER = "https://workspace-auth.example.test"


class KeyResolver:
    def get_signing_key_from_jwt(self, token: str) -> SimpleNamespace:
        return SimpleNamespace(key=KEY.public_key())


def token(**overrides: object) -> str:
    return jwt.encode(
        {
            "sub": "invited-user",
            "iss": ISSUER,
            "aud": ISSUER,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "role": "authenticated",
            "email": "invited@example.test",
            **overrides,
        },
        KEY,
        algorithm="EdDSA",
        headers={"kid": "test-ed25519"},
    )


def verifier() -> OIDCJWKSVerifier:
    return OIDCJWKSVerifier(
        jwks_url=f"{ISSUER}/.well-known/jwks.json",
        issuer=ISSUER,
        audience=ISSUER,
        algorithm="EdDSA",
        subject_roles={"invited-user": ["analyst"]},
        key_resolver=KeyResolver(),
    )


def test_neon_roles_are_assigned_by_subject_not_token_metadata() -> None:
    principal = verifier().verify(token(role="admin", roles=["admin"]))
    assert principal.roles == frozenset({Role.ANALYST})


@pytest.mark.parametrize(
    "overrides",
    [
        {"sub": "uninvited-user"},
        {"aud": "other-app"},
        {"iss": "other-issuer"},
        {"banned": True},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
    ],
)
def test_neon_rejects_uninvited_or_invalid_identity(overrides: dict[str, object]) -> None:
    with pytest.raises(AuthenticationRequiredError):
        verifier().verify(token(**overrides))


def test_neon_configuration_requires_asymmetric_jwks() -> None:
    settings = Settings(
        _env_file=None,
        AUTH_ENABLED=True,
        AUTH_JWT_ALGORITHM="EdDSA",
        AUTH_JWKS_URL=f"{ISSUER}/.well-known/jwks.json",
        AUTH_JWT_ISSUER=ISSUER,
        AUTH_JWT_AUDIENCE=ISSUER,
        AUTH_SUBJECT_ROLES={"invited-user": ["analyst"]},
    )
    assert settings.auth_subject_roles["invited-user"] == ["analyst"]
