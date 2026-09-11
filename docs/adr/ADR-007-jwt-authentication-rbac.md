# ADR-007: Signed JWT authentication and role-based API controls

- Status: Accepted
- Date: 2026-09-11

## Context

V7C introduced durable human review but accepted an unauthenticated reviewer identifier from the
client. V8B needs a credible identity boundary without building a password product, user database,
or vendor-specific SSO integration.

## Decision

Protected routes resolve an `AuthenticatedPrincipal` from a bearer JWT through a `TokenVerifier`
protocol. The built-in verifier uses one explicitly configured HS256 secret or RS256 public key
and fixed algorithm, validates signature, issuer, audience, expiry, and non-empty subject, then
maps only known analyst/reviewer/admin roles. Health and readiness stay public.

Assessment and knowledge routes require authentication. Review listing and approve/reject/request
revision require reviewer or admin. Audit identity is derived from the verified principal; client
`reviewer_id` is retained only for historical compatibility. New nullable columns preserve old
V7C rows while recording assessment creator subject and reviewer subject, email, role, issuer, and
request ID for new authenticated activity. Production cannot disable authentication silently.

## Consequences

The API exposes an OpenAPI HTTP bearer scheme and returns correlated structured 401/403 errors.
Bearer tokens and claims are excluded from logs. The application has an OIDC-friendly verifier
seam but V8B does not fetch JWKS, perform discovery/rotation/revocation, provision users, implement
ABAC or tenancy, or claim cryptographic non-repudiation.
