# Observability and privacy boundary

The application persists structured runtime telemetry with each governed assessment and can
export a compact OpenTelemetry span through OTLP/HTTP. `OBSERVABILITY_EXPORTER=none` is the default;
set it to `otlp` with `OTEL_EXPORTER_OTLP_ENDPOINT` to use an OpenTelemetry Collector or compatible
backend.

The exporter allowlist includes request/assessment IDs, execution mode and health, durations,
model/embedding/tool counts, retry/timeout/degradation counts, retrieval modes, provider-reported
token counts, gate decision, risk level, review state, and termination reason. It excludes prompts,
responses, source text, embeddings, chain-of-thought, authorization headers, identity claims,
secrets, and exception messages. Export failure is logged by type and never changes the persisted
assessment outcome.

Recommended operational views:

- request rate, error rate, and p50/p95/p99 latency by route;
- readiness failures and database connection saturation;
- provider latency, timeouts, retries, and reported token use;
- gate decisions, pending-review age, and block/rejection counts;
- retrieval degradation, graph fallback, and connector sync failures.

Alert thresholds must be calibrated with real traffic. External observability SaaS, sampling,
tail-based policies, log shipping, and on-call integration remain deployment decisions rather than
hard-coded vendor dependencies.
