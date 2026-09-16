# Enterprise Product Interface

## Purpose

V8C turns the existing architecture and risk platform into an operable product without adding new
AI intelligence. The interface makes persisted assessments, evidence, runtime decisions,
evaluations, and human-review state understandable to an analyst or reviewer. FastAPI remains the
authoritative boundary for validation, orchestration, persistence, risk policy, and authorization.

## Runtime shape

```text
Browser
  |
  | HTTPS / page navigation + /backend/* API calls
  v
Next.js server (Vercel production; non-root container locally)
  |
  | server-side rewrite to Render, X-Request-ID, bearer JWT when configured
  v
FastAPI on Render (platform port, non-root container)
  |
  +--> PostgreSQL + pgvector
  +--> existing provider abstractions
```

Next.js uses a same-origin `/backend/*` rewrite. In local development it targets
`http://127.0.0.1:8000`; Compose builds it with `http://api:8000`; Vercel receives the Render API
HTTPS URL through the server-side `API_INTERNAL_URL` variable. This keeps preview deployments
same-origin and avoids exposing a container hostname or secret to the browser. The backend's CORS
allowlist explicitly permits the two production frontend domains and still applies to direct API
access.

## Product surfaces

- **Dashboard:** database-backed lifecycle, gate-decision, and review counts plus recent work.
- **Assessments:** bounded pagination, status filtering, execution mode, risk state, and ownership.
- **New assessment:** the existing structured request contract and bounded file-ingestion API.
- **Assessment detail:** recommended architecture, risks, controls, human oversight, evidence,
  source excerpts, execution trace, operational telemetry, and runtime gate reasons.
- **Review queue:** reviewer/admin-only pending work and exact persisted candidate inspection.
- **Evaluation:** the existing deterministic V7A retrieval and V7B architecture/risk aggregates,
  clearly labelled as synthetic rather than production assurance.
- **Operations:** safe runtime checkpoint summaries and request IDs; no prompts, tokens, private
  reasoning, credentials, full documents, or raw provider payloads.
- **Public demo:** `/demo` presents static synthetic architecture, evidence, risk, evaluation,
  runtime-governance, HITL, and operations examples without mounting the authentication provider or
  making an API call.

## Trust and security boundaries

The client has one typed API module. It attaches a bounded request ID and, when present, a bearer
token. Tokens are held only in `sessionStorage`, which limits them to the current browser tab; they
are not placed in source, URLs, cookies, local storage, telemetry, or logs. The login view validates
the token by calling the authenticated `/api/v1/session` endpoint.

The `/demo` path sits outside that client boundary. It does not initialize session discovery, read
`sessionStorage`, or render review mutations. Its examples are version-controlled fictional data
and confer no analyst, reviewer, or administrator authority.

Navigation is role-aware for clarity, but it is not the security control. FastAPI independently
requires a verified principal on product APIs and reviewer/admin roles on queues, candidates,
history, and decisions. Client-provided reviewer identity is never trusted. Review actions require
an explicit confirmation and operate on the exact durable candidate selected by the runtime gate.

Enterprise content is rendered as text through React; there is no raw HTML injection path. Error
views show stable backend messages and correlation IDs rather than stack traces or configuration.
The UI does not store chain-of-thought and does not expose the model's private reasoning.

## State and API design

The UI deliberately avoids a second business-state model. Creation, ingestion, assessment detail,
runtime status, review history, and review actions use existing V1–V8B endpoints. V8C adds only
bounded read models needed for product navigation:

- `GET /api/v1/session`
- `GET /api/v1/assessments?status=&offset=&limit=`
- `GET /api/v1/reviews/pending`
- `GET /api/v1/assessments/{id}/review-candidate`
- `GET /api/v1/evaluation/summary`

Assessment lists contain compact metadata, not full results or source content. Evidence excerpts
are fetched only when a user opens the relevant assessment. The evaluation summary runs the
version-controlled, network-free fixture harness; it makes no provider request.

## Quality and deployment

Frontend CI installs the exact lockfile and runs ESLint, TypeScript, Vitest, and a production Next.js
build. Tests cover authenticated request behavior, correlation/error handling, role-aware navigation,
public-demo isolation and interaction, confirmation before review mutation, and safe rendering of
script-like or prompt-injection content.
The Compose smoke job builds and starts the frontend with PostgreSQL, migrations, and FastAPI, then
checks API readiness, frontend liveness, and the rendered product shell. Compose waits for the API
healthcheck before starting the frontend, and the frontend container exposes its own network-free
`GET /health` liveness check.

The UI is responsive and keyboard-focusable, with semantic form labels and status text. It uses a
small internal component system and no remote font, analytics, or component CDN, keeping the local
product deterministic and minimizing third-party surface area.

## Deliberate limitations

V8D adds deployable cloud manifests and backend OIDC/JWKS token verification, but the frontend still
accepts an already issued bearer token; it does not implement an IdP authorization-code/PKCE login
flow. Managed secret injection belongs to the hosting platform. Tenant isolation, OCR,
spreadsheets, presentations, malware scanning, queues, and background jobs remain absent.
Assessment creation remains synchronous, and future UI changes must preserve these backend trust
boundaries. Live-provider quality is not implied by the deterministic evaluation screen.
