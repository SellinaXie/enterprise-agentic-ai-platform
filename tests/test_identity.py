"""JWT authentication, RBAC, and authenticated reviewer identity tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_assessment_service, get_runtime_governance_service
from app.core.config import Settings
from app.identity.models import AuthenticatedPrincipal, Role
from app.main import create_app
from app.runtime.models import HumanReviewAction, HumanReviewStatus
from tests.test_assessments import VALID_REQUEST

SECRET = "synthetic-test-signing-key-with-more-than-32-characters"
ISSUER = "https://identity.test.invalid/"
AUDIENCE = "enterprise-agentic-ai-platform"


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        APP_ENV="test",
        APP_LOG_LEVEL="ERROR",
        AUTH_ENABLED=True,
        AUTH_JWT_SECRET=SECRET,
        AUTH_JWT_ISSUER=ISSUER,
        AUTH_JWT_AUDIENCE=AUDIENCE,
        PROVIDER_REQUIRED=False,
    )


def _token(
    *,
    subject: str = "principal-123",
    roles: list[str] | None = None,
    issuer: str = ISSUER,
    audience: str = AUDIENCE,
    expires_at: datetime | None = None,
    secret: str = SECRET,
    extra: dict[str, object] | None = None,
) -> str:
    claims: dict[str, object] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "exp": expires_at or datetime.now(UTC) + timedelta(minutes=5),
        "roles": roles or ["analyst"],
        "email": "principal@example.test",
        "name": "Synthetic Principal",
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, secret, algorithm="HS256")


class AssessmentServiceStub:
    principal: AuthenticatedPrincipal | None = None

    def generate_assessment(
        self, request: object, *, principal: AuthenticatedPrincipal | None = None
    ) -> object:
        self.principal = principal
        now = datetime.now(UTC)
        return {
            "assessment_id": uuid4(),
            "status": "pending",
            "input": request,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "completed_at": None,
        }


class GovernanceServiceStub:
    principal: AuthenticatedPrincipal | None = None
    reviewer_id: str | None = None

    def approve(
        self,
        assessment_id: object,
        request: object,
        *,
        principal: AuthenticatedPrincipal | None = None,
    ) -> dict[str, object]:
        self.principal = principal
        self.reviewer_id = request.model_dump().get("reviewer_id")
        return {
            "assessment_id": assessment_id,
            "action": HumanReviewAction.APPROVED,
            "review_status": HumanReviewStatus.APPROVED,
            "assessment_status": "completed",
            "revision_count": 0,
        }


def test_health_remains_public_while_api_requires_bearer_authentication() -> None:
    application = create_app(_settings())
    application.dependency_overrides[get_assessment_service] = AssessmentServiceStub

    with TestClient(application) as client:
        health = client.get("/health")
        protected = client.post(
            "/api/v1/assessments",
            json=VALID_REQUEST,
            headers={"X-Request-ID": "auth-missing-1"},
        )

    assert health.status_code == 200
    assert protected.status_code == 401
    assert protected.headers["www-authenticate"] == "Bearer"
    assert protected.json() == {
        "error": {
            "code": "authentication_required",
            "message": "Valid bearer authentication is required.",
        },
        "request_id": "auth-missing-1",
    }


@pytest.mark.parametrize(
    "token",
    [
        _token(secret="different-synthetic-test-signing-secret-123"),
        _token(issuer="https://wrong-issuer.test.invalid/"),
        _token(audience="wrong-audience"),
        _token(expires_at=datetime.now(UTC) - timedelta(minutes=5)),
        _token(extra={"sub": ""}),
    ],
)
def test_invalid_signed_claim_sets_are_rejected(token: str) -> None:
    application = create_app(_settings())
    application.dependency_overrides[get_assessment_service] = AssessmentServiceStub
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/assessments",
            json=VALID_REQUEST,
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_unsigned_jwt_is_rejected() -> None:
    token = jwt.encode(
        {
            "sub": "unsigned",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "roles": ["admin"],
        },
        key="",
        algorithm="none",
    )
    application = create_app(_settings())
    application.dependency_overrides[get_assessment_service] = AssessmentServiceStub
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/assessments",
            json=VALID_REQUEST,
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 401


def test_cors_preflight_allows_authorization_header() -> None:
    application = create_app(_settings())
    with TestClient(application) as client:
        response = client.options(
            "/api/v1/assessments",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
    assert response.status_code == 200
    assert "Authorization" in response.headers["access-control-allow-headers"]


def test_typed_principal_is_derived_from_valid_claims() -> None:
    service = AssessmentServiceStub()
    application = create_app(_settings())
    application.dependency_overrides[get_assessment_service] = lambda: service
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/assessments",
            json=VALID_REQUEST,
            headers={"Authorization": f"Bearer {_token(roles=['analyst'])}"},
        )

    assert response.status_code == 200
    assert service.principal is not None
    assert service.principal.subject == "principal-123"
    assert service.principal.roles == frozenset({Role.ANALYST})
    assert service.principal.issuer == ISSUER


def test_analyst_cannot_approve_review() -> None:
    application = create_app(_settings())
    application.dependency_overrides[get_runtime_governance_service] = GovernanceServiceStub
    with TestClient(application) as client:
        response = client.post(
            f"/api/v1/assessments/{uuid4()}/reviews/approve",
            json={"reviewer_id": "spoofed", "comment": "Looks good"},
            headers={
                "Authorization": f"Bearer {_token(roles=['analyst'])}",
                "X-Request-ID": "forbidden-1",
            },
        )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"
    assert response.json()["request_id"] == "forbidden-1"


@pytest.mark.parametrize("role", ["reviewer", "admin"])
def test_reviewer_actions_use_authenticated_principal(role: str) -> None:
    service = GovernanceServiceStub()
    application = create_app(_settings())
    application.dependency_overrides[get_runtime_governance_service] = lambda: service
    with TestClient(application) as client:
        response = client.post(
            f"/api/v1/assessments/{uuid4()}/reviews/approve",
            json={"reviewer_id": "spoofed-client-value", "comment": "Approved"},
            headers={"Authorization": f"Bearer {_token(roles=[role])}"},
        )
    assert response.status_code == 200
    assert service.principal is not None
    assert service.principal.subject == "principal-123"
    assert service.principal.audit_role.value == role
    # This confirms the legacy field reaches only the service boundary; production persistence
    # derives reviewer identity from service.principal.
    assert service.reviewer_id == "spoofed-client-value"


def test_openapi_marks_protected_routes_with_bearer_scheme() -> None:
    application = create_app(_settings())
    schema = application.openapi()
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
    assert schema["paths"]["/api/v1/assessments"]["post"]["security"]
    assert "security" not in schema["paths"]["/health"]["get"]
