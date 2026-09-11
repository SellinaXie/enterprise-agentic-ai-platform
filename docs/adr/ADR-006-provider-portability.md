# ADR-006: Narrow provider contracts and built-in adapters

- Status: Accepted
- Date: 2026-09-11

## Context

V1–V8A used OpenAI successfully, but vendor SDK types appeared in assessment, agent, embedding,
and retry code. V8B needs a second structured-reasoning provider without destabilizing the
existing deterministic, single-agent, multi-agent, RAG, and graph paths.

## Decision

Application code depends on two separate contracts: `StructuredModelProvider` and
`EmbeddingProvider`. The first supports schema-constrained output and a bounded single tool-call
decision. The second supports ordered embedding batches. Every adapter publishes capabilities for
structured output, tool calling, usage reporting, and embeddings.

OpenAI implements both contracts. Anthropic implements only structured reasoning/tool selection,
using a forced schema tool for typed output; it is never advertised as an embedding provider.
Vendor clients, response parsing, error normalization, storage options, token-usage extraction,
timeouts, and SDK retry disabling remain inside `app/providers/`. A small configuration factory
selects built-in adapters. Existing OpenAI class names remain as compatibility wrappers.

## Consequences

Workflows can change chat providers independently of the stable pgvector embedding model. Mocked
contract tests remain network-free. Adding a new built-in adapter requires explicit code and
capability validation. Dynamic discovery, third-party plugins, provider fallback/routing, and live
provider benchmarking are outside V8B.
