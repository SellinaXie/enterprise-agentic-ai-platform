# Render API and PostgreSQL deployment

The root `render.yaml` is the backend production contract. It creates one non-root FastAPI Docker
web service and a private PostgreSQL 16 database. The frontend deploys separately to Vercel; see
the [Vercel + Render guide](vercel-render.md).

The API release step runs `alembic upgrade head` before traffic reaches a new revision. The existing
V3 migration executes `CREATE EXTENSION IF NOT EXISTS vector`; Render PostgreSQL 13+ supports
`pgvector`, and PostgreSQL 16 remains the declared baseline. The database does not expose a public
IP allowlist.

## Provision

1. Connect this repository in a Render account and create a Blueprint from `render.yaml`.
2. Review and explicitly select the API and PostgreSQL plans. The repository deliberately does not
   make a paid-plan decision.
3. Enter every `sync: false` value in Render's secret/environment UI. Do not put values in Git.
4. Keep `CORS_ALLOWED_ORIGINS` limited to `https://demo.sellinaxie.com` and
   `https://app.sellinaxie.com`. Vercel preview deployments use the same-origin `/backend` proxy and
   therefore do not require a wildcard origin. Add an exact preview origin only if direct browser
   access is intentionally enabled.
5. Set `TRUSTED_HOSTS` to the hostname of the Render API service, without a URL scheme.
6. Configure an RS256 identity provider using `AUTH_JWKS_URL`, `AUTH_JWT_ISSUER`, and
   `AUTH_JWT_AUDIENCE`. The issuer must place `analyst`, `reviewer`, or `admin` in `roles` (or
   `role`).
7. Add `OPENAI_API_KEY` for the current embedding and default chat providers. Provider credentials
   stay in Render's secret store.
8. Deploy, then verify `/health` returns liveness and `/readiness` confirms configuration,
   PostgreSQL connectivity, Alembic head, and required tables.

The Blueprint intentionally omits compute plans and cannot create an account on the user's behalf.
Render applies its current defaults to new resources, which may be billable. Keep public database
access disabled (`ipAllowList: []`). Render's current extension documentation lists `pgvector` and
enables it with `CREATE EXTENSION vector`, which matches the existing migration.

## Release and rollback

The pre-deploy migration is forward-only. Before a schema-changing release, create and verify a
backup using the operations runbook. If application code is unhealthy but the migration is
backward compatible, roll the service back to the last known-good image/revision. Prefer a new
forward migration for schema defects. Use `alembic downgrade` only after its exact path has been
rehearsed on a restored database and the data-loss implications are understood.

The optional `.github/workflows/deploy.yml` uses a protected GitHub `production` environment and a
Render deploy hook. Configure `RENDER_DEPLOY_HOOK_URL` and `DEPLOYMENT_HEALTH_URL` as environment
secrets only when automated release is desired. Blueprint auto-deploy may be used instead; do not
enable both without an intentional release policy.

## Honest boundary

The repository contains a verified deployment manifest, but a live URL requires the repository
owner to authorize a Render account, select plans, and provide identity/provider secrets. A
successful local/CI build is not evidence of cloud capacity, availability, or a tested recovery
time.

References: [Render Blueprint specification](https://render.com/docs/blueprint-spec) and
[Render PostgreSQL extensions](https://render.com/docs/postgresql-extensions).
