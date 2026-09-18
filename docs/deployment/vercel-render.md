# Vercel frontend + Render backend deployment

This is the intended public-demo architecture:

```text
demo.sellinaxie.com/demo ─┐
                         ├─ Vercel / Next.js ── /backend/* rewrite ── Render / FastAPI
app.sellinaxie.com ──────┘                                      │
                                                                └─ Render PostgreSQL 16 + pgvector
```

The public showcase (`/`, `/demo`, `/architecture`) is static content. None of it mounts the
authentication provider, reads a JWT, or calls the backend, so it renders the same whether or not
the Render API is deployed. The application routes (`/dashboard` and onward) retain the existing
JWT/OIDC/RBAC boundary. Both domains can point to one Vercel project: use the showcase routes for
`demo.sellinaxie.com` and `/dashboard` onward for the authenticated product on
`app.sellinaxie.com`. No account, domain, plan, or secret is created by repository code.

## 1. Deploy the backend and database to Render

1. In Render, create a Blueprint from the repository's root `render.yaml`.
2. Review and explicitly select the API and PostgreSQL plans. The repository deliberately does not
   make a paid-plan decision.
3. Confirm the database is PostgreSQL 16 and remains private. The existing Alembic chain enables
   `vector` and owns all schema changes.
4. Supply the `sync: false` settings in Render—not in Git:
   - `OPENAI_API_KEY`
   - `AUTH_JWKS_URL`
   - `AUTH_JWT_ISSUER`
   - `AUTH_JWT_AUDIENCE`
   - `TRUSTED_HOSTS` (the Render API hostname only)
5. Keep the Blueprint CORS value explicit:
   `https://demo.sellinaxie.com,https://app.sellinaxie.com`.
6. Deploy. Render runs `alembic upgrade head` as the pre-deploy command and starts the existing
   `python -m app.server` production entrypoint.
7. Record the Render API HTTPS URL for Vercel. Do not place database or provider credentials in a
   frontend variable.

Verify before connecting the frontend:

```bash
curl --fail-with-body https://RENDER_API_HOST/health
curl --fail-with-body https://RENDER_API_HOST/readiness
```

`/health` proves process liveness. `/readiness` additionally checks production configuration,
database connectivity, current Alembic head, and required tables. A ready response is the pgvector
schema deployment checkpoint; an application smoke test below exercises retrieval behavior.

## 2. Deploy the Next.js frontend to Vercel

1. Import the same GitHub repository as a Vercel project.
2. Set **Root Directory** to `frontend`.
3. Keep Framework Preset **Next.js**. The checked-in `vercel.json` uses `npm ci` and
   `npm run build`; no output directory override is required.
4. Use the Node version supported by `frontend/package.json` (`>=24`).
5. Add these Vercel environment variables for Production and Preview:

| Variable | Value | Exposure |
| --- | --- | --- |
| `API_INTERNAL_URL` | Render API HTTPS URL | Server-side rewrite only |
| `NEXT_PUBLIC_API_BASE_URL` | `/backend` | Safe public relative path |
| `NEXT_PUBLIC_APP_URL` | `https://app.sellinaxie.com` | Optional public navigation URL |

`frontend/production.env.example` records the non-secret shape for reference; do not upload it as a
secret bundle or replace hosting-platform environment management with a committed production file.

The browser calls `/backend`; Next.js proxies that path to `API_INTERNAL_URL`. This avoids exposing
credentials (there are none in that URL), keeps preview deployments same-origin, and avoids broad
CORS patterns. Never put JWTs, provider keys, database URLs, deploy hooks, or OIDC client secrets in
a `NEXT_PUBLIC_*` variable.

Deploy and first verify the Vercel-generated production URL:

```bash
curl --fail-with-body https://PROJECT.vercel.app/health
curl --fail-with-body https://PROJECT.vercel.app/
curl --fail-with-body https://PROJECT.vercel.app/demo
curl --fail-with-body https://PROJECT.vercel.app/architecture
```

The frontend `/health` route confirms the Next.js process only. The landing page, guided demo, and
architecture overview are fully usable even when the API is unavailable; that is intentional safe
separation, not evidence that the backend is ready.

## 3. Connect custom domains and DNS

In Vercel **Project → Settings → Domains**, add:

- `demo.sellinaxie.com`
- `app.sellinaxie.com`

Do not change domain ownership or DNS until the owner approves. Vercel shows the exact record for
each hostname; for externally managed DNS this is normally a CNAME for each subdomain. Copy the
values Vercel displays rather than relying on a hardcoded target. Preserve unrelated DNS records.
After propagation, Vercel verifies the records and automatically provisions TLS certificates.

Verify:

```bash
dig +short demo.sellinaxie.com
dig +short app.sellinaxie.com
curl --fail-with-body https://demo.sellinaxie.com/demo
curl --fail-with-body https://app.sellinaxie.com/health
```

Use Vercel's domain inspection screen (or `vercel domains inspect`) to confirm **Valid
Configuration**, then check that both URLs negotiate HTTPS without a certificate warning. The
showcase's canonical public link is `https://demo.sellinaxie.com/demo`, alongside `/` and
`/architecture` on the same domain. The authenticated app is served from
`https://app.sellinaxie.com/dashboard`.

## 4. Temporary Vercel domains and CORS

Preview and generated `*.vercel.app` deployments should retain
`NEXT_PUBLIC_API_BASE_URL=/backend`. Their browser traffic is same-origin and the Vercel server-side
rewrite calls Render, so no wildcard CORS rule is needed. If a preview must call Render directly,
temporarily add that one exact HTTPS origin to `CORS_ALLOWED_ORIGINS`, redeploy the API, test it, and
remove it afterward. Production validation rejects unrestricted `*` CORS.

## 5. End-to-end smoke test

Run after Render readiness, Vercel deployment, DNS, and HTTPS are all independently healthy:

1. Open `https://demo.sellinaxie.com/demo` in a private browser session.
2. Walk through all seven stages: architecture, evidence, risk, evaluation, governance, HITL, and
   operations.
3. Confirm the page never requests `/api/v1/session`, stores a token, or exposes an action that can
   approve/reject a review. Repeat this check for `/` and `/architecture`.
4. Open `https://app.sellinaxie.com/dashboard`; confirm the OIDC/JWT login boundary appears.
5. Authenticate with an analyst account and create a low-risk synthetic assessment.
6. Confirm POST/GET persistence, evidence references, execution metadata, and request ID.
7. With a reviewer test account, create a high-risk synthetic assessment and verify the runtime
   gate pauses it for review. Approve only synthetic test data and confirm the audit identity.
8. Check `/readiness`, Render logs, and OTLP telemetry for safe operational fields only.
9. Confirm no secret, bearer token, prompt, full document, embedding, raw provider error, or private
   reasoning appears in browser assets or logs.

## Rollback boundary

Vercel can promote or roll back a frontend deployment independently. Render can roll back API code
when migrations remain backward compatible. Before schema changes, follow the backup/restore
runbook. Prefer a forward corrective migration; never point tests or destructive commands at the
production database.

References: [Vercel project settings](https://vercel.com/docs/project-configuration/project-settings),
[Vercel custom domains](https://vercel.com/docs/domains/set-up-custom-domain),
[Vercel SSL](https://vercel.com/docs/domains/working-with-ssl),
[Render Blueprint specification](https://render.com/docs/blueprint-spec), and
[Render PostgreSQL extensions](https://render.com/docs/postgresql-extensions).
