# Render deployment

The root `render.yaml` is the production deployment contract for a Render Blueprint. It creates
two non-root Docker web services and a private PostgreSQL 16 database. The API release step runs
`alembic upgrade head` before traffic reaches a new revision; the frontend reaches the API through
Render's private service address. PostgreSQL enables `pgvector` through the existing Alembic
migrations.

## Provision

1. Fork or connect this repository in a Render account and create a Blueprint from `render.yaml`.
2. Enter every `sync: false` value in Render's secret/environment UI. Do not put values in Git.
3. Set `CORS_ALLOWED_ORIGINS` to the exact public frontend origin and `TRUSTED_HOSTS` to the API
   hostname. Neither may contain `*` in production.
4. Configure an RS256 identity provider using `AUTH_JWKS_URL`, `AUTH_JWT_ISSUER`, and
   `AUTH_JWT_AUDIENCE`. The issuer must place `analyst`, `reviewer`, or `admin` in `roles` (or
   `role`).
5. Add `OPENAI_API_KEY` for the current embedding and default chat providers. Provider credentials
   stay in the hosting secret store.
6. Deploy, then verify `/health`, `/readiness`, the frontend `/health`, login, one low-risk
   assessment, and one review workflow.

The Blueprint intentionally omits compute plans and cannot create an account on the user's behalf.
Render applies its current defaults to new resources, which may be billable; review and select
service/database plans, region, retention, and high availability before approving the Blueprint.
Keep public database access disabled (`ipAllowList: []`).

## Release and rollback

The pre-deploy migration is forward-only. Before a schema-changing release, create and verify a
backup using the operations runbook. If application code is unhealthy but the migration is
backward compatible, roll the services back to the last known-good image/revision. Prefer a new
forward migration for schema defects. Use `alembic downgrade` only after its exact path has been
rehearsed on a restored database and the data-loss implications are understood.

The optional `.github/workflows/deploy.yml` uses a protected GitHub `production` environment and
Render deploy hook. Configure `RENDER_DEPLOY_HOOK_URL` and `DEPLOYMENT_HEALTH_URL` as environment
secrets only when automated release is desired. Blueprint auto-deploy may be used instead; do not
enable both without an intentional release policy.

## Honest boundary

The repository contains a verified deployment manifest, but a live URL requires the repository
owner to authorize a Render account, select a database plan, and provide identity/provider
secrets. A successful local/CI build is not evidence of cloud capacity, availability, or a tested
recovery time.
