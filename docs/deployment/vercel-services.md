# Full-stack Vercel deployment

This option deploys Next.js and FastAPI together using Vercel Services (Beta).
The existing Render deployment remains an alternative.

## Project settings

- Use the repository root as the Vercel Root Directory (clear `frontend`).
- Select the Services framework. Build/install commands belong to each service in root `vercel.json`.
- Frontend: `frontend`, Next.js, `npm ci`, `npm run build`.
- Backend: repository root, FastAPI, ASGI entrypoint `app.main:app`.

The platform routes `/backend/*` to FastAPI and removes the `/backend` prefix.
Other requests go to Next.js. Browser calls continue to use `/backend/api/v1/*`.
The public showcase and `/demo` remain independent of the backend.

Do not set `API_INTERNAL_URL` for the Services configuration. It is only needed
for the separate Vercel frontend + Render backend option. Keep
`NEXT_PUBLIC_API_BASE_URL=/backend` if configuring the public API path explicitly.

## Required private configuration

Configure values directly in Vercel, separately for Production and Preview:

- `DATABASE_URL`: a reachable PostgreSQL database with the Alembic schema applied.
- `OPENAI_API_KEY` (or the selected `ANTHROPIC_API_KEY` for chat; embeddings still use OpenAI).
- `AUTH_JWT_ALGORITHM`, either `AUTH_JWKS_URL` or `AUTH_JWT_VERIFICATION_KEY`,
  `AUTH_JWT_ISSUER`, and `AUTH_JWT_AUDIENCE` for the existing token issuer.
- `TRUSTED_HOSTS`: exact custom domains and any additional production aliases.

The Vercel entrypoint enforces production validation and authentication. It adds
the generated deployment host and canonical production host to the exact host allowlist.
It never turns authentication off to make a demo load.

`python -m scripts.check_vercel_settings` runs during the backend build. It
rejects missing/placeholder production configuration without printing secret inputs.
It does not run database migrations or create identities. Apply `alembic upgrade head`
against the intended database through the owner's migration workflow, then verify
readiness. Never run migrations against an unverified production database.

## Verification before production promotion

1. `/` and `/demo` render; guided demo links resolve to `/demo`.
2. `/health` reports frontend liveness.
3. `/backend/health` returns backend JSON with `status: ok`.
4. `/backend/readiness` returns `status: ready`, including database and schema readiness.
5. `/backend/api/v1/session` without a token returns 401, rather than 404.
6. With an existing analyst identity, create and retrieve a synthetic assessment.
7. Verify reviewer access is still role restricted before promoting a tested production build.

## Managed sign-in

Set `NEXT_PUBLIC_AUTH_MODE=neon`, `NEON_AUTH_BASE_URL` and a private, randomly
generated `NEON_AUTH_COOKIE_SECRET` to use invited-email verification codes.
Production and Preview use separate Neon branches, URLs, cookies and database
credentials. Registration is closed; create invited identities in Neon first.
No visitor receives a workspace role automatically.

The browser uses the same-origin `/api/auth/*` SDK proxy and HTTP-only session
cookies. A fresh short-lived JWT is requested for backend calls. Application page
layouts check the server session; FastAPI independently validates the signature,
issuer, audience, expiry and assigned workspace role.

Neon uses EdDSA. Set `AUTH_JWT_ALGORITHM=EdDSA`, `AUTH_JWKS_URL` to the branch's
JWKS endpoint, and both `AUTH_JWT_ISSUER` and `AUTH_JWT_AUDIENCE` to the **origin**
of the branch's auth URL (without its database/auth path). Leave
`AUTH_JWT_VERIFICATION_KEY` unset or empty. `AUTH_SUBJECT_ROLES` is a private JSON
map of provisioned identity IDs to application roles, for example
`{"invited-user-id":["analyst"]}`. Assign the owner's exact identity ID explicitly;
never use first-signup-as-admin or trust Neon's generic `authenticated` role.

Without managed mode, the existing signed bearer-token login remains available
for local development and deployments using their own token issuer.
