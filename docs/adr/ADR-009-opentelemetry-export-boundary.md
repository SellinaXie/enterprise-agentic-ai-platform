# ADR-009: Privacy-safe OpenTelemetry export boundary

Status: Accepted

Use OTLP/HTTP behind a small application exporter interface and keep it disabled by default. Export
only an explicit allowlist of operational IDs, counts, timings, execution state, gate outcome, and
provider-reported token counts. Never export prompts, source content, model output, embeddings,
private reasoning, credentials, or raw exceptions.

Exporter outages do not change assessment persistence or governance decisions. A deployment may
send OTLP to an OpenTelemetry Collector and choose a backend independently.
