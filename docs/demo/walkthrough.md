# Portfolio demo walkthrough

This 8–10 minute walkthrough uses synthetic data and no live model calls.

## Prepare

Start the Compose stack, apply migrations, then create two deterministic records:

```bash
docker compose up --build --detach postgres migrate api frontend
docker compose exec api python scripts/seed_demo.py
```

Open `http://localhost:3000`. In an authenticated environment use an `admin` or `reviewer` token.

## Story 1 — customer-facing AI with PII

Open **Synthetic Retail Bank**. Explain that a plausible architecture is not automatically safe to
release: the candidate identifies high privacy risk and customer-facing PII, recommends human
authority, and the centralized gate returns `REQUIRE_HUMAN_REVIEW`. Show the risk reasons,
content-free telemetry, persisted candidate, and reviewer audit workflow. Approve or reject it and
show the immutable-style event history and authenticated actor.

## Story 2 — low-risk internal assistant

Open **Synthetic Operations Company**. It performs informational policy discovery, has no external
action, and carries a low operational risk with citation/escalation controls. The same gate returns
`AUTO_COMPLETE`, illustrating that governance is proportional rather than a mandatory manual
queue for every AI use case.

## Architecture discussion

Show the architecture overview, then explain why deterministic, single-agent, and multi-agent
modes coexist. Complexity is earned by the task. Point out separate chat/embedding provider
contracts, PostgreSQL/pgvector persistence, optional GraphRAG, read-only connector, OIDC/JWKS RBAC,
OTLP export, and recovery runbook.

## Claims to avoid

The synthetic evaluation and demo validate contracts and intended control flow. They do not prove
production model quality, regulatory compliance, cloud availability, tenant isolation, or a
measured RPO/RTO. Live provider quality and a real cloud recovery drill remain deployment work.
