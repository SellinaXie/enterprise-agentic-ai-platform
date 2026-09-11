# Security Policy

## Project status

This repository is a production-minded portfolio and reference implementation. It is not a
certified production service and does not replace an organization's security, privacy, risk, or
compliance controls.

V8B adds signed-JWT verification, typed principals, analyst/reviewer/admin authorization, and
authenticated review audit attribution to the V8A container, configuration, logging,
error-handling, and database foundations. It is not a complete enterprise identity platform:
external OIDC/JWKS discovery and rotation, identity provisioning, revocation, tenant isolation,
ABAC, managed-secret integration, deployment hardening, and continuous production monitoring are
not implemented.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's private vulnerability
reporting feature when it is enabled for this repository. Otherwise, contact the repository owner
through the contact method on their GitHub profile and ask for a private reporting channel before
sharing technical details.

Do not include real credentials, API keys, client data, proprietary documents, regulated data, or
working exploit payloads in a public issue. There is no claim of a staffed enterprise incident
response team or guaranteed response time.

## Secrets and data

Use environment variables or a deployment platform's secret injection. Never commit `.env`, real
database passwords, provider keys, production documents, or customer assessment data. Rotate any
credential immediately if it is accidentally disclosed.

Production configuration requires authentication, an explicit issuer/audience, and a non-placeholder
JWT verification secret or public key. Never log or persist an Authorization header, bearer token,
raw claims object, provider credential, prompt, source document, or embedding. The repository's
conservative secret scan includes OpenAI-style keys, Anthropic-style keys, compact JWTs, private
keys, and obvious password/secret assignments; it complements rather than replaces a managed
secret scanner and repository history review.

The local HS256 verifier is intended for controlled deployments and automated tests. Prefer a
deployment-integrated asymmetric verification key for separated signing authority. V8B does not
fetch remote keys, so operators must rotate configured keys through their deployment secret
mechanism and coordinate token lifetimes. Unsigned tokens and algorithms other than the fixed
configured algorithm are rejected.
