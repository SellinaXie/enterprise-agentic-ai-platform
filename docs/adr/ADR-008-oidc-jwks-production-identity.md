# ADR-008: External OIDC/JWKS production identity

Status: Accepted

Production deployments may validate RS256 access tokens through a configured HTTPS JWKS endpoint
with issuer, audience, expiry, subject, and known-role checks. PyJWT caches resolved signing keys;
unknown keys and invalid claims fail closed. The validated external subject/email/name/role/issuer
map into the existing principal and audit model.

The fixed-key verifier remains for local/test or controlled environments. Exactly one key source
may be configured. User provisioning, refresh tokens, browser authorization-code flow, SCIM, ABAC,
and tenant isolation remain outside the platform.
