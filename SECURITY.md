# Security policy

## Reporting

Do not open a public issue for a suspected vulnerability or include credentials, customer data, or
exploit details in logs/screenshots. Contact the repository owner privately through GitHub and
include the affected revision, impact, minimal reproduction, and suggested mitigation. This
portfolio repository does not advertise a guaranteed response SLA.

## Supported scope

Security fixes target the current `main` branch. The platform is a reference implementation, not a
hosted service or compliance certification. Deployers own threat modeling, data classification,
identity provisioning, network controls, encryption/key management, dependency monitoring,
retention, incident response, and regulatory review.

## Built-in boundaries

Production requires PostgreSQL, authentication, explicit hosts/origins, and safe provider secrets.
OIDC/JWKS tokens validate algorithm, issuer, audience, expiry, subject, and known roles. Reviewer
identity comes from verified claims. Tools and loops are bounded; connector access is read-only and
configured; telemetry excludes content; source provenance and runtime gates are persisted. The
application does not store chain-of-thought.

Never commit `.env`, tokens, database dumps, private keys, production documents, screenshots with
credentials, or provider responses containing sensitive data. Rotate any credential that may have
entered Git history rather than merely deleting the file.

## Secrets, data, and verification

Inject secrets through environment variables or the deployment platform. Never log or persist an
Authorization header, bearer token, raw claims object, provider credential, prompt, source
document, model conversation, or embedding. The conservative repository scan checks common
provider/GitHub/AWS token shapes, compact JWTs, private keys, and obvious credential assignments;
it complements rather than replaces managed scanning and Git-history review.

Prefer external RS256/JWKS identity for production signing-key rotation. Exactly one JWKS or fixed
verification-key source may be configured. This application validates access tokens but does not
issue tokens, manage users, implement SCIM, or provide tenant isolation. The fixed HS256 mode is
intended for tests or controlled environments with separated secret handling.

The policy connector credential should have read access only to the smallest required repository
scope. The configured base URL—not a caller-provided URL—defines the network destination. Run
backup restore drills against isolated targets; never point test or restore rehearsals at the
production database.
