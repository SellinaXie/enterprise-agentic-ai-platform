# Architecture Overview

## Platform purpose

The **Enterprise AI Architecture & Risk Intelligence Platform** turns enterprise business context
and internal knowledge into structured, evidence-aware architecture assessments. It is designed as
a general enterprise AI architecture platform with an intentionally strong risk and governance
emphasis: it helps evaluate whether AI is appropriate, what architecture fits, which risks and
controls matter, where evidence is missing, and when a human must make the final decision.

The platform is not a generic chatbot. Its primary output is a validated assessment covering
solution architecture, integrations, operational complexity, risk, governance, human oversight,
and information gaps. It supports simple deterministic workflows as well as bounded single-agent
and specialist multi-agent execution, so architectural complexity can match the problem rather
than becoming the default.

## End-to-end architecture

```text
Enterprise documents + business context
                   |
                   v
       Validate, parse, normalize, chunk
                   |
                   v
        PostgreSQL 16 + pgvector
          |                    |
          v                    v
      Vector RAG       Knowledge Graph / GraphRAG
          |                    |
          +---------+----------+
                    v
       Deterministic | Single-Agent | Multi-Agent
                    |
                    v
       Architecture + Risk/Governance Analysis
                    |
                    v
        Typed Synthesis + Provenance Validation
                    |
                    v
       V7A/V7B Evaluation + Runtime Telemetry
                    |
                    v
        Central Deterministic Runtime Risk Gate
             |                      |
       complete/warn          review/block
             |                      |
             +----------+-----------+
                        v
          Authenticated Human Review (HITL)
                        |
                        v
           Durable, Attributed Audit History
```

Documents enter through plain-text or bounded file-ingestion APIs. The current parsers accept
digital PDFs, DOCX, UTF-8 text, and Markdown; they normalize content, preserve page or section
provenance, create deterministic chunks, generate embeddings, and optionally enrich the knowledge
graph. Original upload bytes are not persisted.

At assessment time, validated business context becomes a controlled retrieval query. Vector RAG
finds semantically relevant chunks, while GraphRAG adds bounded entity relationships and impact
paths. Retrieved context remains attributable to source document and chunk identifiers. The
configured execution mode then produces architecture and risk/governance analysis. A deterministic
flow handles straightforward cases; a single agent can choose from two read-only knowledge tools;
or a multi-agent graph separates evidence, architecture, risk/governance, and synthesis roles.

All paths converge on the same typed assessment contract. Citation sanitization removes invented
or duplicate provenance before persistence. Evaluation code measures retrieval and assessment
quality outside the production request path. During a live assessment, a centralized deterministic
risk gate decides whether the result may complete, should carry a warning, requires human review,
or must be blocked and escalated. Reviewers authenticate with signed JWTs, authorization is enforced
by role, and decisions are appended to a durable audit history using identity derived from the
verified principal rather than client-supplied reviewer data.

## Why the major components exist

### Data and grounding

- **PostgreSQL** is the transactional system of record for assessment lifecycle state, knowledge
  documents and chunks, graph entities and relationships, runtime checkpoints, review events, and
  identity attribution. Keeping these related models in one database preserves transactional
  consistency and simplifies migrations, backup planning, and operations.
- **pgvector** adds native embedding storage and cosine-similarity search without introducing a
  separate vector database. It is appropriate for the current scale and keeps vector evidence
  aligned with its relational provenance.
- **RAG** supplies enterprise evidence to the assessment instead of asking a model to rely only on
  general knowledge. Controlled context construction and source identifiers make claims easier to
  inspect, validate, and cite.
- **Knowledge Graph / GraphRAG** represents typed relationships among systems, processes, policies,
  risks, controls, roles, and other enterprise entities. Bounded traversal can expose dependencies
  and impact chains that similarity search alone may miss. Graph claims retain source-chunk
  provenance, and PostgreSQL remains the graph store until workload evidence justifies a dedicated
  graph database.

### Execution and quality

- **LangGraph** provides explicit state, routing, finite loops, parallel specialist fan-out, and
  deterministic fan-in for agent workflows. It makes orchestration and failure paths inspectable
  without introducing an unconstrained supervisor agent.
- **Single-agent mode** supports problems where one reasoning loop benefits from selectively using
  knowledge tools, but separate specialists would add more coordination cost than value.
- **Multi-agent mode** separates evidence retrieval, solution architecture, risk/governance, and
  synthesis when those responsibilities benefit from distinct contracts and trust boundaries.
  Architecture and risk specialists run independently, and synthesis reconciles their typed
  outputs into the shared result.
- **The evaluation harness** provides repeatable, version-controlled comparisons. It tests
  retrieval, provenance, architecture fit, risk and control coverage, groundedness, unsupported
  claims, abstention, governance quality, degraded behavior, and specialist preservation.
- **Runtime governance** converts validated execution signals into one consistent policy decision.
  It ensures a technically successful model response is not automatically treated as an approved
  enterprise decision.
- **Human-in-the-loop review (HITL)** creates a durable pause-and-review boundary for higher-risk or
  insufficiently supported results. Approval finalizes the exact persisted candidate; rejection and
  revision requests remain auditable events rather than overwriting history.

### Portability, access, and operations

- **Provider abstraction** keeps vendor SDK objects inside adapters. Structured chat-model behavior
  and embeddings use separate contracts because organizations may change reasoning providers while
  retaining a stable embedding model and vector index. OpenAI currently implements both contracts;
  Anthropic implements structured reasoning and tool selection, not embeddings.
- **JWT and RBAC** establish a stateless identity boundary. Signed tokens are checked for algorithm,
  signature, issuer, audience, expiry, subject, and known roles. Analysts can use protected APIs;
  reviewer and admin roles control review operations. Health and readiness remain public.
- **Docker and CI** make the production-like topology and validation repeatable. Containers separate
  PostgreSQL, migrations, and the non-root API process. GitHub Actions verifies linting, formatting,
  compilation, dependencies, deterministic regressions, real PostgreSQL/pgvector behavior,
  migrations, package and image builds, and health/readiness behavior on every push and pull request.

## Architecture judgment and tradeoffs

The governing principle is **complexity is earned, not assumed**. A fixed transformation or simple
rules decision can be safer, cheaper, faster, and easier to audit as deterministic code. The
deterministic assessment path therefore remains a first-class option, and both agent flags default
off.

Single-agent execution is useful when bounded tool choice materially improves context gathering.
Multi-agent execution is justified only when independent evidence, architecture, and governance
analysis improves control coverage or exposes meaningful disagreement. More agents also introduce
latency, cost, more failure surfaces, and synthesis risk; multi-agent is not inherently better.

Risk and governance breadth must be balanced against architectural simplicity and groundedness.
Producing more risks or controls is not valuable if they are irrelevant, unsupported, or obscure
missing evidence. The platform therefore evaluates precision as well as coverage, penalizes
unsupported claims and unnecessary complexity, and rewards appropriate abstention.

Chat-model and embedding-provider abstractions are intentionally separate. Switching a reasoning
model should not silently require re-embedding the corpus or invalidate the vector index. This
boundary also avoids advertising capabilities a provider does not supply.

## Current production foundation

The backend runs on Python 3.12 and FastAPI, with a non-root Docker image and a Compose topology for
the API, PostgreSQL 16 with pgvector, and an explicit Alembic migration job. Health checks distinguish
process liveness from readiness; readiness verifies configuration, database connectivity, migration
head, and required tables without calling a model provider or exposing database errors.

The HTTP boundary includes bounded request IDs, structured JSON logging, sanitized errors, explicit
CORS and trusted-host settings, graceful provider and database disposal, request and upload limits,
and production configuration validation that fails closed for unsafe database, provider, logging,
host, or authentication settings. Signed JWT authentication protects assessment and knowledge APIs,
while RBAC restricts human-review controls and persisted identity fields attribute creation and
review actions.

GitHub Actions runs network-free unit, workflow, and evaluation regressions alongside a real
PostgreSQL/pgvector integration suite and container smoke tests. Alembic validates both an empty
database upgrade and the current migration downgrade/upgrade boundary.

## Evaluation strategy

- **V7A retrieval evaluation** compares vector, graph, and hybrid retrieval using a synthetic,
  version-controlled corpus. Metrics include Hit Rate@K, Precision@K, Recall@K, MRR, entity and
  relationship hits, path success, provenance coverage, and negative-query false positives.
- **V7B architecture and risk evaluation** compares deterministic, single-agent, and multi-agent
  outputs across synthetic enterprise scenarios. It measures architecture fit, over-engineering
  avoidance, risk recall and precision, severity consistency, control and governance coverage,
  groundedness, unsupported claims, human-oversight accuracy, abstention, and synthesis quality.
- **V7C runtime governance** adds operational signals, bounded retries and timeouts, safe degradation,
  centralized risk decisions, durable checkpoints, and auditable human review. It turns quality and
  risk conditions into runtime controls rather than another offline score.

These deterministic fixtures validate contracts, metrics, orchestration, and expected tradeoffs.
They are not production assurance, regulatory certification, or evidence of live model quality.

## Security and governance boundaries

The platform stores typed outputs and compact execution events, **not chain-of-thought**, raw model
conversations, prompts, embeddings, bearer tokens, or full tool arguments. Document, chunk, entity,
and relationship provenance supports traceability, while final citation sanitization rejects
unobserved references.

Tools are static, read-only, schema-validated, and bounded by explicit per-agent permissions,
timeouts, step limits, and call limits. Architecture, risk/governance, and synthesis specialists
receive no tools. Provider or retrieval failures degrade safely with controlled error categories;
missing specialist output is disclosed rather than fabricated.

The runtime risk gate can warn, require authenticated review, or block and escalate based on risk,
evidence, provenance, mitigation, and execution health. Review events are append-only at the
repository boundary and retain reviewer subject, email, role, issuer, request ID, decision, and
bounded comments. These controls support accountability but do not replace an organization's
security, privacy, legal, risk, or compliance program.

## Current limitations

- There is no frontend yet and no live cloud deployment.
- Full tenant isolation, tenant-aware authorization, quotas, and data partitioning are not present.
- OCR and image-only PDF ingestion are not supported; neither are Excel or PowerPoint ingestion.
- There are no external enterprise connectors for document stores, ticketing, messaging, or GRC.
- Production SSO, enterprise IdP discovery/JWKS rotation, provisioning, and revocation are deferred.
- There is no external observability SaaS, managed alerting, or production incident integration.
- Live-provider architecture, risk, and retrieval quality has not been benchmarked; current
  benchmark results use deterministic synthetic fixtures.

## Next stages

- **V8C — Enterprise Product UI:** build the authenticated interface for assessments, evidence,
  runtime decisions, and human review without weakening the existing backend boundaries.
- **V8D — Deployment, enterprise integration, and portfolio hardening:** add a real cloud deployment,
  production identity integration, managed secrets and observability, enterprise connectors, and
  operational hardening supported by deployment evidence.
