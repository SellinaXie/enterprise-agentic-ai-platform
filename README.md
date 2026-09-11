# Enterprise AI Architecture & Risk Intelligence Platform

Production-minded V8A backend for grounded enterprise AI architecture assessments. V8A preserves
the complete V1-V7C implementation and adds reproducible containerization, real
PostgreSQL/pgvector integration, CI, deployment health boundaries, configuration hardening,
request correlation, and production-safe logging/error handling. Architecture remains the broad
purpose of the platform; enterprise risk, controls, and governance are first-class dimensions
rather than a replacement compliance-checking product.

## V8A Production Foundation

V8A is the infrastructure/application production foundation, not the completion of V8. It adds a
non-root Python 3.12.12 API image, PostgreSQL 16 with pgvector 0.8.6, an explicit migration service, a
separate test database, GitHub Actions integration validation, readiness checks, production
profile validation, bounded request IDs, explicit CORS/trusted hosts, JSON logging, sanitized
errors, and graceful resource disposal. It does not change the V3–V7C AI execution architecture.

### Container quickstart

Docker Engine with the Compose plugin is the only local infrastructure prerequisite; PostgreSQL
does not need to be installed on the host.

```bash
cp .env.example .env
# Replace the local placeholder password. Add a real provider key only if exercising AI routes.
docker compose up --build --detach
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/readiness
```

Compose starts:

- `postgres`: persistent PostgreSQL/pgvector application database plus a separately initialized
  `enterprise_ai_test` database.
- `migrate`: one explicit forward-only `alembic upgrade head` job.
- `api`: the non-root production image after PostgreSQL is healthy and migration succeeds.
- `integration-tests`: an opt-in `test` profile built with test-only dependencies.

Normal API startup never performs a hidden downgrade or destructive reset. For production,
execute the migration image as a release job before shifting traffic; coordinate backups and
rollback plans separately. V8A does not implement backup/restore or disaster-recovery automation.

Run the real PostgreSQL suite against the disposable Compose test database:

```bash
docker compose --profile test run --rm integration-tests
```

The test guard requires `TEST_DATABASE_URL` to use PostgreSQL, contain `test` in its database
name, differ from `DATABASE_URL`, and not resemble a production database. The suite validates the
empty-to-head migration chain, a `0005 → 0004 → 0005` round trip, native UUID/JSONB/TIMESTAMPTZ,
pgvector `vector(1536)` and HNSW behavior, assessment persistence, graph foreign keys/uniqueness
and bounded traversal, V7C checkpoints, approval, revision history, and restart/session
boundaries.

For local network-free development without Docker:

```bash
pytest -m "not postgres"
ruff check .
ruff format --check .
```

To stop the stack while preserving the application database, run `docker compose down`. Add
`--volumes` only when intentionally deleting local Compose database data.

### Liveness and readiness

- `GET /health` is process liveness only. It does not query PostgreSQL or OpenAI.
- `GET /readiness` checks critical configuration, database connectivity, Alembic head
  `20260910_0005`, and required tables. It returns HTTP 503 with only `ready`/`not_ready` states
  when any check fails. It never calls OpenAI or exposes a DSN, credential, SQL error, or traceback.

### Configuration and HTTP boundary

`APP_ENV` supports `development`, `test`, `staging`, and `production` (with `local` retained for
compatibility). Production rejects debug/traceback logging, missing or non-PostgreSQL
`DATABASE_URL`, obvious placeholder credentials, wildcard CORS/trusted hosts, incomplete pricing,
and a missing provider key when the provider is required by enabled features. Development and
test retain safe opt-in defaults. `PROVIDER_REQUIRED=false` is intended only for infrastructure
or deterministic test processes that make no provider calls.

`X-Request-ID` accepts only a bounded alphanumeric/`.`/`_`/`-` value; otherwise a UUID is
generated. The ID is returned as a response header, added to request logs, and persisted in safe
assessment execution/runtime telemetry. Existing error bodies remain compatible when no incoming
ID is supplied; when a valid ID is supplied it is also returned in the structured error body.
Unexpected errors return only a stable code, safe message, and correlation ID. JSON request
`Content-Length`, domain strings, reviewer comments, upload bytes, and metadata are bounded;
deployment proxies must additionally enforce streaming/chunked request limits.

For direct development, use `uvicorn app.main:app --reload`. The image runs
`uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`; request logging is handled by
the application's structured middleware. A production reverse proxy must validate/replace
forwarded headers, send an allowed `Host`, enforce body/time limits, and configure Uvicorn's
trusted forwarded IPs for that specific network rather than trusting arbitrary clients. Shutdown
closes the lazy provider client and disposes SQLAlchemy pools; request-scoped sessions and upload
handles retain their existing explicit cleanup boundaries.

JSON logs include timestamp, level, event, request ID, assessment ID where available, status, and
duration. Sensitive field names, prompts, private reasoning, embeddings, full documents,
authorization data, provider messages, secrets, and production tracebacks are excluded. Secrets
must be injected through environment variables or the deployment platform and must never be baked
into the image. `pyproject.toml` declares supported direct-dependency ranges; `constraints.txt`
pins the direct versions validated by V8A for repeatable container and CI installation without
claiming a fully locked transitive supply chain.

### CI boundary

`.github/workflows/ci.yml` runs on every push and pull request. It fails on lint, formatting,
compile, dependency, unit/workflow/evaluation regression, migration, PostgreSQL/pgvector, OpenAPI,
secret-scan, package-build, image-build, or Compose-smoke failures. PostgreSQL tests run against a
real pgvector service in CI; V7A/V7B remain deterministic and the optional LLM judge is disabled.
No live provider call is required.

V8A is a production-minded reference implementation, not certification for regulated production
use and not a substitute for organizational security/compliance controls. Authentication,
RBAC/ABAC, SSO, authenticated reviewer identity, provider portability, tenant isolation, frontend,
cloud deployment, managed secrets, backup automation, and external observability remain deferred.

## Runtime Reliability & Risk Controls

The platform no longer assumes that every AI-generated assessment should automatically become a
final decision. After generation, schema validation, synthesis, and provenance sanitization, one
central framework-neutral gate evaluates lightweight structured signals and returns exactly one
of `auto_complete`, `complete_with_warning`, `require_human_review`, or
`block_and_escalate`. Machine-readable reason codes explain every non-automatic outcome.

The default policy auto-completes low-risk candidates, completes medium-risk candidates with a
warning, sends high-risk candidates to human review, and blocks critical-risk candidates. Missing
required evidence, degraded execution, unavailable specialists, tool/retrieval failures, missing
expected oversight, and detectable unsupported claims can strengthen the decision. High-risk
invalid provenance and critical risk without mitigation block completion. Policy thresholds and
condition switches are configuration, not banking-specific rules or a regulatory framework.

`RUNTIME_RISK_GATE_ENABLED=false` preserves V1–V7B behavior. When enabled, review-required
candidates move to the explicit `pending_review` assessment state. The public assessment result
remains null while the validated candidate, execution metadata, gate decision, and telemetry are
stored in `assessment_runtime_states`. This is a durable application-level checkpoint shared by
all three execution modes; it does not claim provider-side continuation or replay an LLM call.

Review actions are additive endpoints:

```text
GET  /api/v1/assessments/{id}/runtime-status
GET  /api/v1/assessments/{id}/reviews
POST /api/v1/assessments/{id}/reviews/approve
POST /api/v1/assessments/{id}/reviews/reject
POST /api/v1/assessments/{id}/reviews/request-revision
```

Approval finalizes the exact persisted validated candidate. Rejection stores only a stable safe
failure. A revision request preserves the candidate and all earlier events, increments a bounded
counter, and can be resumed only through the trusted internal revision path after a new candidate
has been generated and validated. Reviewer IDs and comments are optional bounded strings;
comments are untrusted audit content and are never executed, added to system prompts, or allowed
to change tool permissions. `human_review_events` is append-only at the repository boundary.

Provider operations use explicit per-call model, embedding, and graph-extraction timeouts plus
bounded retries for recognized timeouts, connection failures, rate limits, and selected provider
5xx failures. Validation and other permanent failures are not retried. Approved read-only tools
run through a configurable timeout boundary and return the safe `tool_timeout` error. Failure
categories are controlled values; provider exception text is never returned to clients.

Operational telemetry records counters and durations only: execution mode and health, execution
and human-wait latency, model and embedding calls, model-call durations, tool calls, vector/graph
use, specialist and synthesis durations, retries, timeouts, degradation, termination, gate and
review events, and provider-reported tokens when available. Cost remains `null` unless explicit
input/output prices are configured. Telemetry never contains prompts, private reasoning,
embeddings, source documents, tool arguments, secrets, or raw provider messages. These fields
support future evidence-based mode comparisons; this repository makes no live performance claim.

```dotenv
RUNTIME_RISK_GATE_ENABLED=false
RUNTIME_MEDIUM_RISK_DECISION=complete_with_warning
RUNTIME_HIGH_RISK_DECISION=require_human_review
RUNTIME_CRITICAL_RISK_DECISION=block_and_escalate
RUNTIME_REVIEW_ON_INSUFFICIENT_EVIDENCE=true
RUNTIME_REVIEW_ON_DEGRADED_EXECUTION=true
RUNTIME_REVIEW_ON_SPECIALIST_UNAVAILABLE=true
RUNTIME_REVIEW_ON_TOOL_FAILURE=true
RUNTIME_BLOCK_HIGH_RISK_INVALID_PROVENANCE=true
RUNTIME_BLOCK_CRITICAL_MISSING_MITIGATION=true
MAX_HUMAN_REVISIONS=2

PROVIDER_MAX_RETRIES=2
PROVIDER_RETRY_BASE_DELAY_MS=250
MODEL_TIMEOUT_SECONDS=30
EMBEDDING_TIMEOUT_SECONDS=30
TOOL_TIMEOUT_SECONDS=10
GRAPH_EXTRACTION_TIMEOUT_SECONDS=30
# Leave unset unless explicit current pricing is maintained.
# MODEL_INPUT_COST_PER_1M_TOKENS=0.00
# MODEL_OUTPUT_COST_PER_1M_TOKENS=0.00
```

V7C human review is a workflow control, not a security boundary. It does not provide authenticated
reviewer identity, enterprise RBAC/ABAC, SSO, tenant isolation, or cryptographic approval
assurance. V8A adds the production foundation described above but not identity, authorization,
frontend, hosted deployment, external monitoring SaaS, LangSmith, MCP, or enterprise secrets
infrastructure.

## V7B architecture and risk/governance quality evaluation

```text
10 synthetic enterprise scenarios + explicit expected labels
                              │
                              ▼
     deterministic  vs  single_agent  vs  multi_agent
                              │
                              ▼
 architecture fit + risk/control/governance + grounded claims
                              │
                              ▼
 per-case metrics → mode reports → Pareto comparison + tradeoffs
                              │
                              └── optional, explicitly enabled LLM judge
```

The version-controlled benchmark at
`app/evaluation/datasets/v7b_assessment_benchmark.json` contains ten fictional cases: a
customer-service assistant handling PII, confidential internal RAG, external API tools,
high-impact lending support, a third-party AI vendor, compliance review, human-operated
recommendations, low-risk productivity assistance, missing evidence, and a simple deterministic
rules workflow. It uses no customer, banking-client, proprietary, or copyrighted policy data.

Run one mode or compare all three without PostgreSQL, OpenAI, the internet, or external datasets:

```bash
python -m app.evaluation.assessment.runner --mode deterministic
python -m app.evaluation.assessment.runner --mode single_agent
python -m app.evaluation.assessment.runner --mode multi_agent
python -m app.evaluation.assessment.runner --all
```

Mode reports are written to `outputs/evaluation/v7b_<mode>.json`; the complete run also writes
`outputs/evaluation/v7b_comparison.json`. Reports expose all cases, safe failures, degraded cases,
unsupported metrics, judge status, warnings, non-secret configuration, and a SHA-256 fingerprint
of deterministic results. Runtime reports remain ignored by Git.

### V7B controlled taxonomies

The finite risk taxonomy is: privacy, security, model risk, hallucination/grounding, compliance,
operational risk, access control, data governance, third-party/vendor risk, explainability, human
oversight, monitoring, and auditability.

The finite control taxonomy is: retrieval grounding, role-based access control, least privilege,
tool allowlisting, human approval, escalation, audit logging, data minimization, model monitoring,
output validation, fallback behavior, versioning, approval gates, vendor due diligence, and
incident response. These vocabularies exist for repeatable benchmark scoring; they do not claim to
be a regulatory standard or complete GRC framework.

### V7B deterministic metrics

- **Risk recall** is expected risk categories identified divided by all expected risks.
- **Risk precision** is expected risk categories identified divided by all unique evaluable risks
  identified. Unexpected and explicitly unacceptable categories therefore reduce precision.
- **Severity consistency** is severity matches divided by matched expected risks.
- **Control coverage** and **governance coverage** are matched explicit expectations divided by
  all expected controls or governance requirements.
- **Human-oversight accuracy** is one when the recommendation matches the case expectation. It
  penalizes both missing required oversight and unnecessary oversight.
- **Architecture fit** is matched explicit architecture characteristics divided by all expected
  characteristics. Expectations include when RAG, graph retrieval, an agent, multiple agents, or
  human approval is justified, and when a simpler workflow should be preferred.
- **Over-engineering avoidance** is one for a simple-workflow case when the recommendation avoids
  asserting agent or multi-agent necessity. It is `N/A` when simplicity is not a test objective.
- **Groundedness** is validly supported normalized claims divided by all emitted evaluable claims.
  Support must trace to allowed assessment input, retrieved evidence, an existing specialist
  finding, or an allowed general-knowledge category.
- **Unsupported claim rate** is claims without any benchmark-valid support divided by all emitted
  evaluable claims. Unknown claims, invented references, and disallowed support types fail.
- **Appropriate abstention** checks explicit uncertainty, refusal to invent a conclusion, and a
  validation recommendation when evidence is insufficient; unnecessary abstention is also
  penalized.
- **Specialist preservation** and **synthesis transparency** apply to multi-agent fixtures. They
  test preservation of important existing specialist findings, surfaced disagreements, rejection
  of invented findings, and disclosure of unavailable/degraded inputs.

Metrics are macro-averaged independently; unavailable dimensions remain JSON `null` and display as
`N/A`. The comparison uses a per-case Pareto frontier instead of a hidden global score. It can
therefore show deterministic sufficiency, agent improvements, ties, or failures without hardcoding
a winner. "Complexity is earned, not assumed" is tested directly by the two simple cases.

### Optional model-based judge

`EVALUATION_LLM_JUDGE_ENABLED=false` by default. A provider call requires both that environment
flag, an explicit CLI `--llm-judge`, and `OPENAI_API_KEY`; tests never enable it. The judge uses a
strict schema and separate 1–5 rubrics for groundedness, risk reasoning, mitigation usefulness,
architecture appropriateness, governance completeness, and clarity/actionability. Evaluated
content is delimited as untrusted data and cannot grant tools or change instructions. Results are
labeled model-based opinions, never ground truth, and contain only concise rationales—not
chain-of-thought. The report records the judge model, call count, and SDK token counters when the
provider exposes them directly.

The default fixture profile evaluates declared normalized outputs, including synthetic specialist
handoffs and degraded states. It validates the harness and illustrates controlled tradeoffs; it
does not measure a live model or production deployment. In particular:

```text
Synthetic benchmark performance
≠
real-world production assurance
```

The V7B evaluation release added no endpoint, database table, migration, agent role, tool
permission, or runtime quality gate. V7C adds the runtime controls described above and still does
not execute benchmark content during production assessment requests.

## V7A deterministic retrieval evaluation

```text
version-controlled synthetic corpus + queries + expected evidence
                              │
                              ▼
                  typed benchmark validation
                              │
             ┌────────────────┼────────────────┐
             ▼                ▼                ▼
        vector service    graph service    hybrid service
             └────────────────┼────────────────┘
                              ▼
 ranked evidence + entities + relationships + provenance
                              │
                              ▼
 per-case metrics → macro aggregates → JSON reports + comparison
```

The benchmark at `app/evaluation/datasets/v7a_retrieval_benchmark.json` contains eight fictional
enterprise documents, nine queries, stable document/chunk identities, controlled entities and
relationships, known relevant evidence, expected paths, and transparent deterministic fixture
rankings. The queries cover semantic facts, policy lookup, multiple documents, impact chains,
multi-hop relationships, and one negative/no-answer case. None of the documents represents an
actual company policy or regulation, and no generated embedding is stored in the dataset.

Run one mode or the complete deterministic comparison without PostgreSQL, an API key, or network
access:

```bash
python -m app.evaluation.runner --mode vector
python -m app.evaluation.runner --mode graph
python -m app.evaluation.runner --mode hybrid
python -m app.evaluation.runner --all
```

Each mode writes `outputs/evaluation/v7a_<mode>.json`; `--all` also writes
`outputs/evaluation/v7a_comparison.json`. Runtime reports are ignored by Git. They contain a UTC
timestamp, execution profile, dataset version, compatible/skipped cases, per-case observations,
aggregate metrics, non-secret retrieval settings, and warnings. The CLI prints the same calculated
metrics concisely and renders unsupported comparison values as `N/A` rather than zero.

### Metric definitions

- **Hit Rate@K** is one when at least one unique expected document/chunk appears in the first K
  results, otherwise zero.
- **Precision@K** is the number of unique relevant results in the first K divided by K. The fixed K
  denominator is retained when fewer than K results are returned.
- **Recall@K** is the number of unique expected results retrieved in the first K divided by all
  expected results.
- **MRR** is the reciprocal rank of the first expected result in the evaluated top K, or zero when
  no expected result appears.
- **Entity Hit Rate** and **Relationship Hit Rate** are the fractions of expected entity names and
  exact typed relationship edges present in a graph neighborhood.
- **Path Success** is the fraction of expected bounded paths whose required typed edges all appear.
- **Provenance Coverage** is the fraction of returned evidence and graph claims whose document,
  chunk, title, and relationship-source identities match the version-controlled corpus.
- **Negative-query false-positive rate** is the fraction of negative cases returning any evidence.
  Positive rank metrics exclude negative cases, so a retriever is not rewarded for always
  returning content.

Duplicate chunk identities are counted once at their first rank. Aggregate values are macro
averages over cases for which a metric is defined. Hybrid reports also count evidence whose origin
is `vector`, `graph`, or `both`. Every comparison value comes from its mode report; no outcome is
hardcoded into the comparison utility.

The configuration snapshot records embedding model and dimensions, top K, similarity threshold,
chunk size and overlap, graph depth, graph confidence, and graph entity limit. It never records API
keys, database URLs, embeddings, source text, or prompts.

The default execution profile uses explicit deterministic retrieval doubles and the real V6
hybrid merge service. Its results validate the dataset, runner, metric formulas, provenance, and
mode behavior; they are labeled synthetic and are not claims about live semantic quality. A live
OpenAI/PostgreSQL evaluation was unavailable and is reported as skipped rather than fabricated.
Retrieval evaluation is not final-answer quality evaluation.

### V7A portfolio status

Implemented: deterministic retrieval evaluation, vector metrics, graph retrieval metrics, hybrid
retrieval comparison, negative-query measurement, and provenance validation.

Implemented in V7B: final assessment architecture/risk/governance evaluation and optional
model-based judging. Implemented in V7C: internal operational telemetry, bounded resilience,
central runtime gating, and durable human review. V8A now provides the production foundation.

## V6.5 enterprise document ingestion

```text
Multipart file upload
        │
        ▼
size + filename + extension + MIME + signature validation
        │
        ▼
parser router ──→ PDF | DOCX | UTF-8 TXT | Markdown
        │
        ▼
ParsedDocument (normalized source text + provenance segments)
        │
        ▼
existing V3 normalization → content hash → chunk → embed → persist
        │
        └── optional existing V6 graph enrichment
        │
        ▼
vector RAG / hybrid GraphRAG → Evidence Agent
```

`POST /api/v1/knowledge/files` accepts multipart uploads while the existing
`POST /api/v1/knowledge/documents` plain-text API remains unchanged. The adapter allowlists file
types, reads no more than the configured byte limit, validates lightweight format signatures,
extracts text and provenance, and delegates normalization, chunking, embeddings, transactions,
and persistence to the existing V3 service. File ingestion enables normalized SHA-256 content
deduplication, so equivalent extracted text reuses the first stored document and its embeddings.

PDF extraction supports digitally generated PDFs and records page provenance. Image-only or
insufficiently extractable PDFs return the explicit `ocr_required` error; V6.5 performs no OCR or
image understanding. DOCX parsing preserves headings, paragraph order, and table text. Markdown
keeps headings, paragraphs, lists, and fenced code as source text while recording section headings.
TXT accepts strict UTF-8, including a UTF-8 BOM, and preserves meaningful line structure before
the shared normalizer runs.

Original file bytes and temporary paths are never persisted. Client filenames are reduced to a
safe basename and treated as display metadata, not a filesystem destination. Extension, reported
MIME type, and signatures must agree. Uploaded content remains untrusted evidence: it is not
executed and receives the existing RAG and agent prompt-injection boundaries.

### V6.5 portfolio status

Implemented: plain-text, PDF, DOCX, TXT, and Markdown ingestion; metadata and provenance
extraction; vector RAG; GraphRAG; and the existing multi-agent workflows.

Current limitation: image-only and scanned PDFs require OCR and are not supported by V6.5.

Implemented later: V7C reliability controls and the V8A production foundation. MCP or external
enterprise integrations remain deferred unless later evidence justifies them.

## V6 capability

V6 models enterprise relationships without introducing a second database:

```text
knowledge_documents → knowledge_chunks ──────┐
        │                    │                │
        │                    ├── entity mentions
        │                    └── relationship provenance
        │                                     │
        └── pgvector similarity       relational graph traversal
                          └──────────┬──────────┘
                                     ▼
                      provenance-preserving hybrid context
```

`knowledge_entities` uses a controlled entity taxonomy: organization, process, system, policy,
regulation, risk, data asset, AI capability, control, role, and other. Identity resolution is
deliberately conservative: Unicode-normalized whitespace and case variants merge only when their
entity types also match. It does not perform fuzzy, model-directed, or semantic entity merging.

`knowledge_entity_mentions` links every resolved entity to the exact existing document and chunk
where it appeared. `knowledge_relationships` stores a directed edge from the controlled `uses`,
`depends_on`, `part_of`, `governed_by`, `affected_by`, `creates_risk`, `mitigated_by`, `requires`,
`produces`, `consumes`, or `related_to` vocabulary. Every relationship has a confidence value and
mandatory source-chunk provenance; unsupported types, unknown entity references, and self-edges
are rejected.

Entity and relationship extraction uses closed Pydantic structured-output contracts over one
existing V3 chunk at a time. The model receives only the chunk, its identifier, the controlled
schema, and for relationships the entity keys already accepted from that chunk. Confidence
thresholding, normalization, deduplication, provenance validation, and persistence are application
code responsibilities. Extraction does not request or retain chain-of-thought.

Graph search accepts a plain query, never SQL or a graph query language. It resolves known entity
names deterministically, traverses incoming and outgoing relationships breadth-first, and enforces
configured depth, entity-count, and confidence bounds. Hybrid retrieval runs vector and graph paths
independently, deduplicates by source chunk, and labels internal evidence as `vector`, `graph`, or
`both`. Graph-only evidence has no fabricated similarity score. Context separates `VECTOR
EVIDENCE`, `GRAPH RELATIONSHIPS`, and `SOURCE EVIDENCE` so graph claims remain attributable.

The multi-agent Evidence Agent alone can receive `search_knowledge_graph`; V4 retains its exact two
tools. Safe execution metadata records counts, depth, degraded mode, and public error codes—not
queries, source text, embeddings, prompts, provider messages, or hidden reasoning. If graph
retrieval fails, vector evidence remains usable; if vector retrieval fails, graph evidence remains
usable; if both fail, assessment generation continues from request data only.

### PostgreSQL instead of Neo4j

PostgreSQL is the intentional V6 graph store. The graph is modest, highly provenance-oriented,
transactional with the existing knowledge layer, easy to migrate with Alembic, and queried through
bounded application-owned repository operations. A separate Neo4j service would add operations,
security, consistency, backup, and synchronization costs before the workload demonstrates a need
for specialized large-scale graph algorithms or graph-query workloads. That tradeoff can be
revisited from evidence later; no Neo4j integration exists in V6.

## V5 capability

V5 separates four genuinely different reasoning responsibilities. It does not add agents merely
to increase agent count: evidence retrieval has a distinct trust and tool boundary; solution
architecture and risk/governance need independent analysis; and final synthesis must reconcile
those typed conclusions into the existing business contract. LangGraph is the orchestrator—there
is no fifth LLM supervisor and agents do not exchange free-form messages.

```text
Assessment Service
        │
        ▼
     LangGraph
        │
  initialize
        │
 Evidence Agent ── read-only knowledge tools ── V3 retrieval/repositories
        │
        ├───────────────────────┐
        ▼                       ▼
Architecture Agent      Risk & Governance Agent
      (no tools)                (no tools)
        └───────────┬───────────┘
                    ▼
             Synthesis Agent
                 (no tools)
                    │
                 validate
                    │
                    ▼
       Existing AssessmentResult + safe execution metadata
```

The `architecture` and `risk_governance` nodes are true parallel LangGraph branches after evidence
is complete. A list-form fan-in edge waits for both branches and schedules `synthesis` once. The
branches write to separate typed state keys, so convergence never depends on completion order.

### Four specialist contracts

- **Evidence Agent** receives the assessment, the two allowed tool definitions, and only evidence
  it has observed. It may run a bounded one-tool-per-step loop and returns `EvidenceBrief` with
  evidence items, gaps, qualitative confidence, and observed document/chunk identifiers. It does
  not design or produce the final assessment.
- **Solution Architecture Agent** receives only the assessment and typed `EvidenceBrief`. It has no
  tools and returns `ArchitectureRecommendation`: pattern, components, data flow, integrations,
  complexity, assumptions, alternatives, simplicity rationale, and confidence.
- **Risk & Governance Agent** receives only the assessment and typed `EvidenceBrief`, independently
  of the architecture branch. It has no tools and returns `RiskGovernanceReview`: risk level,
  findings, controls, human oversight, auditability, unresolved questions, and confidence.
- **Synthesis Agent** receives the assessment, typed specialist outputs, explicit missing-output
  facts, and allowed evidence provenance. It has no tools, reconciles disagreement in favor of the
  safer bounded recommendation under uncertainty, and returns the unchanged `AssessmentResult`.

All specialist business handoffs are closed Pydantic schemas. Each OpenAI specialist output uses
the Responses API structured-output parser; the bounded configured retry applies only to
recognized transient provider failures, not schema validation or an open-ended self-repair loop.
Prompts and raw provider conversations are not passed between agents.

### Execution modes and precedence

```text
MULTI_AGENT_WORKFLOW_ENABLED=false + AGENTIC_WORKFLOW_ENABLED=false
    → deterministic V3 mode

MULTI_AGENT_WORKFLOW_ENABLED=false + AGENTIC_WORKFLOW_ENABLED=true
    → V4 single-agent mode

MULTI_AGENT_WORKFLOW_ENABLED=true
    → V5 multi-agent mode, regardless of the V4 flag
```

Both workflow flags default to `false`; V5 is never mandatory. New execution metadata uses
`deterministic`, `single_agent`, or `multi_agent`. Historical V4 JSON containing `agentic` and
historical rows with no execution metadata remain readable.

### Failure and degraded-mode policy

- Evidence failure produces an explicit low-confidence assessment-only `EvidenceBrief`; both
  downstream specialists can continue.
- Architecture failure leaves that handoff absent. Risk review and synthesis may continue without
  inventing architecture analysis.
- Risk/governance failure leaves that handoff absent, marks the run degraded, lowers the visible
  governance confidence through a limitation, and does not silently claim a review occurred.
- Synthesis is required. Its failure fails the assessment unless the bounded structured-output
  retry succeeds.
- Successful completion requires synthesis and at least one available specialist analysis. The
  configured failure budget can be stricter but can never permit an empty synthesis.

Degradation reasons are added to result information gaps and safe execution metadata. Metadata
includes exactly the four agents, statuses, best-effort durations, safe error codes, unique tool
names, tool-call count, termination, and compact events. It excludes chain-of-thought, prompts,
provider messages, tool arguments, API keys, embeddings, and full documents.

### Tool security and evidence integrity

V5 reuses the V4 registry, strict argument schemas, validation, normalized observations, and
per-execution cache. A separate code permission layer exposes `search_knowledge` and
`get_knowledge_document` only to the Evidence Agent. Architecture, Risk/Governance, and Synthesis
receive no tool schemas; direct unauthorized calls are rejected before the registered handler can
run and produce only a safe `unauthorized_tool` observation.

The Evidence Agent normalizes its provenance to identifiers actually observed from tool results.
Final service-level citation sanitization remains authoritative and removes duplicate or invented
document/chunk references before persistence.

## V4 capability

V4 can route an assessment through one bounded reasoning agent that decides whether existing
context is sufficient, calls one approved read-only knowledge tool at a time when useful, observes
the result, and stops for schema-constrained synthesis. The graph records safe decision/action/
observation events, never private chain-of-thought.

```text
Assessment Service
        │
        ├── AGENTIC_WORKFLOW_ENABLED=false ──→ deterministic V3 RAG flow
        │
        └── AGENTIC_WORKFLOW_ENABLED=true
                         │
                         ▼
                     LangGraph
                         │
             Reason → Tool? → Observe
                │                 │
                └──── Synthesize ←┘
                         │
                         ▼
              Existing AssessmentResult
```

The graph has four explicit nodes: `reason`, `execute_tool`, `synthesize`, and `fail`. Conditional
routing sends only an allowlisted agent decision to the matching node. Every tool observation
returns to the same reasoning agent. Max-step and max-tool-call checks force deterministic
synthesis with available context; an explicit agent failure terminates safely.

### V4 deterministic versus single-agent execution

```dotenv
AGENTIC_WORKFLOW_ENABLED=false
# Existing V3 deterministic request/retrieval/synthesis behavior

AGENTIC_WORKFLOW_ENABLED=true
# V4 LangGraph single-agent reason/act/observe/synthesize behavior
```

The default is `false` when V5 is also disabled. `RAG_ENABLED` continues to control retrieval in
deterministic mode. In single-agent mode the agent chooses whether to invoke retrieval through its
tool registry. Both modes
reuse the same V3 retrieval, evidence, prompt, structured result, and citation-sanitization logic.

### Approved tools

- `search_knowledge(query: str, top_k: int)` calls the V3 `RetrievalService` and returns ranked
  evidence with document ID, chunk ID, title, content, similarity, source type, and metadata.
- `get_knowledge_document(document_id: UUID)` calls the existing read-only document repository
  and returns document provenance plus an excerpt capped at 12,000 characters. A missing document
  is a valid empty observation.

The registry is a static code allowlist. Arguments are validated by closed Pydantic schemas and
are sent to OpenAI as strict function tools with parallel tool calls disabled. Unknown tools and
invalid arguments are rejected before implementation code runs. Identical valid calls in one graph
execution reuse an in-memory result cache and still count toward the finite tool-call limit.

No write, shell, arbitrary file, arbitrary SQL, arbitrary network, code-execution, or side-effect
tool exists. The preserved V4 path still has exactly one agent and no supervisor/worker pattern.

### Safe execution trace

Single-agent assessments persist one compact JSONB execution summary with `execution_mode`,
`steps_used`, unique `tools_used`, `termination_reason`, and timestamped safe events. Events record
the transition and outcome (for example, tool requested/completed/failed), not model reasoning,
full prompts, tool arguments, secrets, embeddings, or complete documents.

## V3 capability

Plain-text knowledge can be normalized, chunked, embedded with OpenAI, stored in PostgreSQL with
pgvector, searched by cosine similarity, and supplied to the existing structured assessment
generator as attributed evidence. The result records whether external evidence was retrieved and
may cite document/chunk identifiers without exposing embeddings or reproducing complete sources.

```text
Assessment
→ Deterministic Retrieval Query
→ OpenAI Embedding
→ PostgreSQL + pgvector Search
→ Relevant Chunks
→ Controlled RAG Context
→ OpenAI Structured Assessment
→ PostgreSQL Assessment State
```

The architecture stays synchronous to match the existing FastAPI, SQLAlchemy, and OpenAI flow.
No LangChain dependency is used; normalization, chunking, retrieval, and context construction are
small explicit components.

## Knowledge versus application state

The two persistence responsibilities remain separate:

- `assessments` is application state: validated requests, lifecycle status, structured result or
  safe failure, timestamps, and compact execution-mode metadata for new completed assessments.
- `knowledge_documents` and `knowledge_chunks` are V3 retrieval knowledge: normalized source
  text, provenance metadata, deterministic chunks, embeddings, and chunk metadata.
- `knowledge_entities`, `knowledge_entity_mentions`, and `knowledge_relationships` are V6
  relational graph knowledge grounded in those same V3 documents and chunks.

No document, chunk, or vector fields were added to `assessments`. Assessment results contain only
small source references when the model cites retrieved evidence.

## Requirements

- Python 3.12 or newer
- PostgreSQL with the [pgvector extension](https://github.com/pgvector/pgvector) available
- `pip`
- An OpenAI API key for live embedding and assessment generation

V6.5 adds only three runtime dependencies: `pypdf` for digitally encoded PDF text,
`python-docx` for OOXML Word content, and `python-multipart` for FastAPI multipart form parsing.
There is no OCR, spreadsheet, presentation, cloud-storage, or document-AI dependency.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

Create a PostgreSQL database and dedicated application account, then set the Psycopg 3 SQLAlchemy
URL and OpenAI key in `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://enterprise_ai:local-password@localhost:5432/enterprise_ai
OPENAI_API_KEY=
```

Apply the canonical migrations. The V3 migration runs `CREATE EXTENSION IF NOT EXISTS vector`, so
the migration account must be allowed to enable an already installed extension:

```bash
alembic upgrade head
alembic current
alembic history
```

Run the API:

```bash
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`, with OpenAPI documentation at
`http://127.0.0.1:8000/docs`. `GET /health` remains a process liveness check and does not connect
to PostgreSQL or OpenAI.

## Retrieval configuration

```dotenv
RAG_ENABLED=false
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_EMBEDDING_DIMENSION=1536
RAG_CHUNK_SIZE=1200
RAG_CHUNK_OVERLAP=200
RAG_RETRIEVAL_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.35
MAX_UPLOAD_SIZE_MB=10
PDF_MIN_EXTRACTED_CHARACTERS=100

KNOWLEDGE_GRAPH_ENABLED=false
GRAPH_MAX_DEPTH=2
GRAPH_MAX_ENTITIES=20
GRAPH_MIN_CONFIDENCE=0.5

AGENTIC_WORKFLOW_ENABLED=false
AGENT_MAX_STEPS=5
AGENT_MAX_TOOL_CALLS=5
LANGGRAPH_RECURSION_LIMIT=25

MULTI_AGENT_WORKFLOW_ENABLED=false
EVIDENCE_AGENT_MAX_STEPS=4
EVIDENCE_AGENT_MAX_TOOL_CALLS=4
MULTI_AGENT_MAX_FAILURES=2

PROVIDER_MAX_RETRIES=2
PROVIDER_RETRY_BASE_DELAY_MS=250
MODEL_TIMEOUT_SECONDS=30
EMBEDDING_TIMEOUT_SECONDS=30
TOOL_TIMEOUT_SECONDS=10
GRAPH_EXTRACTION_TIMEOUT_SECONDS=30
```

- `text-embedding-3-small` is requested at 1,536 dimensions. The typed setting, ORM vector type,
  and immutable V3 migration agree on this schema dimension. The OpenAI embeddings API supports
  a requested `dimensions` value for `text-embedding-3` models.
- Chunk size and overlap are measured in characters. The deterministic chunker prefers paragraph,
  line, then word boundaries. A 1,200/200 baseline keeps context units readable while retaining
  boundary continuity without adding a tokenizer dependency.
- Retrieval uses cosine similarity and filters results below 0.35 before returning at most five.
- `MAX_UPLOAD_SIZE_MB=10` is a hard multipart file-content limit. Uploads are read incrementally
  and rejected as soon as the limit is exceeded.
- `PDF_MIN_EXTRACTED_CHARACTERS=100` is the conservative threshold below which a non-empty PDF is
  treated as needing OCR rather than accepted as useful text.
- `RAG_ENABLED=false` preserves request-only assessment behavior until pgvector is migrated and
  knowledge has been ingested. Set it to `true` to add retrieval to assessment generation.
- When retrieval returns no qualifying evidence, assessment generation continues from the request
  and explicitly records `external_evidence_status=not_retrieved` with no source references.
- `AGENT_MAX_STEPS` bounds reasoning decisions and defaults to five.
- `AGENT_MAX_TOOL_CALLS` bounds all tool requests, including cache hits, and defaults to five.
- `LANGGRAPH_RECURSION_LIMIT` is an outer graph guard. When agentic mode is enabled it must be at
  least `2 * AGENT_MAX_STEPS + 3`; the default of 25 covers the default workflow limits.
- `EVIDENCE_AGENT_MAX_STEPS` and `EVIDENCE_AGENT_MAX_TOOL_CALLS` independently bound the only V5
  tool loop. Cache hits still count as calls.
- `MULTI_AGENT_MAX_FAILURES` is enforced before synthesis and defaults to two; synthesis still
  requires at least one successfully available specialist analysis.
- `PROVIDER_MAX_RETRIES` applies one centralized bounded transient-failure policy to model,
  embedding, and schema-constrained specialist requests. `OPENAI_MAX_RETRIES` remains accepted as
  a backward-compatible environment alias. Schema-validation failures are never retried.
- `KNOWLEDGE_GRAPH_ENABLED=false` preserves V1-V5 behavior and disables graph extraction,
  traversal, hybrid assessment retrieval, and the Evidence Agent graph tool by default.
- `GRAPH_MAX_DEPTH`, `GRAPH_MAX_ENTITIES`, and `GRAPH_MIN_CONFIDENCE` are hard application-owned
  traversal and acceptance bounds; defaults are two hops, 20 entities, and 0.5 confidence.

## Ingestion

`POST /api/v1/knowledge/documents` accepts plain text and optional provenance metadata:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/documents \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "AI Governance Policy",
    "source_type": "policy",
    "content": "Human review is required for high-impact recommendations.",
    "metadata": {"department": "risk"}
  }'
```

The service normalizes line endings and excess blank lines without summarizing or rewriting the
source, stores the document, creates overlapping chunks, batches embedding requests, validates all
vector dimensions, stores the chunks, and commits the operation atomically.
`GET /api/v1/knowledge/documents/{document_id}` returns the normalized stored document. This
lower-level JSON endpoint remains available for backward compatibility.

Upload an allowlisted enterprise document as multipart form-data:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/files \
  -F 'file=@policy.pdf;type=application/pdf' \
  -F 'title=AI Governance Policy' \
  -F 'source_type=policy' \
  -F 'metadata={"department":"risk"}' \
  -F 'enrich_graph=false'
```

The response identifies the stored document, parser, extraction method, normalized character and
chunk counts, duplicate status, and optional graph-enrichment outcome. `source_type` is the
existing semantic classification (`policy`, `regulation`, `procedure`, and so on); it is separate
from the parser-controlled `file_format` provenance.

| Format | Accepted extension/MIME | Parser | Preserved provenance | Current limitation |
| --- | --- | --- | --- | --- |
| PDF | `.pdf`, `application/pdf` | `pypdf` | page count and per-chunk source pages | text-based PDFs only; image-only/scanned PDFs return `ocr_required` |
| DOCX | `.docx`, OOXML Word MIME | `python-docx` | headings, paragraph/table order, sections | legacy `.doc`, tracked-change interpretation, and image text are unsupported |
| TXT | `.txt`, `text/plain` | strict UTF-8 decoder | filename, MIME, parser metadata | non-UTF-8 files are rejected |
| Markdown | `.md`/`.markdown`, Markdown or safe plain-text MIME | Markdown text parser | headings/sections with original lists and fenced code | no rendered-DOM or embedded-image extraction |

Every adapter returns the closed, format-neutral `ParsedDocument` contract. `text` is the extracted
content passed to V3 normalization; `title`, `filename`, `mime_type`, `file_format`, and semantic
`source_type` identify the knowledge source; optional `page_count` and `sections` describe source
structure; `parser_name`, optional `parser_version`, and `extraction_method` explain how the text
was obtained; `metadata` carries bounded parser facts; and `segments` map page or section context
onto the existing chunks. Format-specific fields remain optional.

The service never writes an upload to a temporary file and never stores its original bytes. It
persists only normalized text and bounded JSONB provenance. Equivalent normalized content is
deduplicated by SHA-256 before new embeddings are requested. PDF page and DOCX/Markdown section
segments are mapped onto overlapping chunks in `knowledge_chunks.metadata`; because existing JSONB
columns are reused, V6.5 requires no schema migration. The shared chunker may span adjacent PDF
pages; such a chunk records the contributing `source_pages` and inclusive page range rather than
creating a second page-specific chunking algorithm.

A duplicate returns the earliest existing document reference with `duplicate=true`, its existing
chunk count, and no new embedding call. The current request filename remains visible in the upload
response, while normalized knowledge identity and the original stored provenance remain attached
to the reused document.

After ingesting a document, opt in to V6 and extract its graph from the already stored chunks:

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/knowledge/documents/DOCUMENT_UUID/graph
```

This synchronous endpoint is idempotent for deterministically identical entities, mentions, and
source-grounded relationships. File clients may instead set `enrich_graph=true` on upload. Vector
ingestion commits first; graph enrichment then reuses that document. If graph enrichment fails,
the response reports a safe degraded status and error code while the V3 document and chunks remain
available.

## Retrieval

`POST /api/v1/knowledge/search` provides a typed semantic-search debugging path:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/knowledge/search \
  -H 'Content-Type: application/json' \
  -d '{"query": "human approval for compliance review", "top_k": 5}'
```

Results are ranked by `1 - cosine_distance` and include chunk/document IDs, document title,
source type, content, score, and document/chunk metadata. Optional `source_type` and `document_id`
filters are supported; V3 does not introduce a search DSL.

`knowledge_chunks.embedding` has an HNSW index using `vector_cosine_ops`. HNSW was selected over
IVFFlat because it offers a useful speed/recall tradeoff and can be created before data exists,
without an index-training step. Default HNSW construction parameters are retained as a clear V3
baseline rather than tuning prematurely.

## Grounded assessment behavior

`POST /api/v1/assessments` retains its V2 lifecycle and adds one explicit V7C pause state when the
runtime gate is enabled:

```text
pending → processing → completed | failed | pending_review
                                      pending_review → completed | failed | revised candidate
```

When RAG is enabled, the service deterministically combines company context, industry, business
problem, current process, pain points, desired outcome, and constraints into one retrieval query.
Ranked chunks are formatted with source boundaries, titles, document IDs, chunk IDs, scores, and
content. System instructions require the model to treat sources as untrusted evidence, separate
facts from inference, state uncertainty, avoid unsupported claims, and prefer the simplest viable
architecture rather than forcing an agentic design.

The service removes duplicate or invented source references from model output before persisting the
structured result. Retrieval or embedding failures produce safe public errors and a durable V2
failed assessment state; credentials, raw provider failures, embeddings, documents, and complete
RAG contexts are not logged.

`GET /api/v1/assessments/{assessment_id}` continues to return the persisted request, structured
result or safe failure, lifecycle timestamps, and safe compatible execution metadata when present.

## Database schema and migration

Alembic revision `20260909_0002` follows the unmodified V2 revision `20260909_0001` and adds:

- `vector` extension enablement when needed.
- `knowledge_documents` with UUID identity, source metadata, normalized `TEXT`, JSONB metadata,
  SHA-256 content hash, and timezone-aware timestamps.
- `knowledge_chunks` with UUID identity, cascading document foreign key, chunk index, `TEXT`,
  `vector(1536)`, JSONB metadata, and timezone-aware creation time.
- Unique `(document_id, chunk_index)` and supporting source, hash, document, and HNSW indexes.

Downgrade removes the HNSW index and knowledge tables but deliberately does not drop `vector`.
PostgreSQL extensions are cluster-level capabilities and may be shared by unrelated schemas.

V4 revision `20260909_0003` follows the unmodified V3 migration and adds only nullable
`assessments.execution_metadata` JSONB storage. It is nullable so deterministic and historical
assessment records retain their existing behavior. Its downgrade removes only that column.

V5 reuses that JSONB column and does not add a migration or agent-run table.

V6 revision `20260910_0004` follows the unmodified V5 head and adds `knowledge_entities`,
`knowledge_entity_mentions`, and `knowledge_relationships` with UUID keys, JSONB metadata,
TIMESTAMPTZ values, controlled-vocabulary checks, confidence checks, uniqueness constraints,
cascading provenance foreign keys, a no-self-edge constraint, and traversal indexes. Downgrade
removes only these three V6 tables in dependency-safe order.

V6.5 adds no tables or columns. File format, parser, extraction, page, and section provenance fit
the existing document/chunk JSONB metadata model, so Alembic head remains `20260910_0004`.

V7A is a version-controlled benchmark and local report layer. It adds no persistence tables and no
migration; Alembic head remains unchanged.

V7B is also a version-controlled benchmark and local report layer. Its normalized quality
contracts deliberately do not modify the stable `AssessmentResult`; Alembic head remains
`20260910_0004`.

V7C revision `20260910_0005` adds `pending_review` to assessment lifecycle values plus
`assessment_runtime_states` for the current durable checkpoint and `human_review_events` for
append-only audit history. Candidate results, gate state, safe execution metadata, and operational
telemetry use PostgreSQL JSONB; IDs use UUID and timestamps use TIMESTAMPTZ. Its downgrade removes
the V7C tables and restores the prior assessment-status vocabulary. Alembic head is
`20260910_0005`.

Alembic is the production schema authority. `Base.metadata.create_all()` is used only for isolated
SQLite tests, where the vector field has a JSON test variant; no SQLite test claims to validate
pgvector operators.

## Testing

```bash
pytest
ruff check .
ruff format --check .
python -m compileall app tests
python -m pip check
alembic history
```

Normal tests use isolated SQLite databases, deterministic synthetic knowledge, deterministic fake
vectors, and mocked OpenAI clients. In addition to V1-V3 coverage, V4 tests cover typed state,
prompt construction, strict schemas, the allowlist, unknown and invalid tool calls, document lookup,
empty/error retrieval, duplicate caching, routing, all graph paths, finite termination, safe traces,
service persistence, and POST/GET round trips through the real graph. No external dataset or
provider network call is required. V5 tests add specialist contract validation, strict context
isolation, tool permissions, bounded Evidence Agent behavior, all success/degraded/failure graph
paths, native parallel fan-out with deterministic fan-in, result/citation safeguards, execution
mode precedence, JSONB metadata persistence, and POST/GET round trips. OpenAI is mocked at the
Responses API boundary.
V6 tests add extraction-contract rejection, conservative entity resolution, source-grounded
relationship persistence, bounded traversal, vector/graph merge labels, independent fallback
paths, GraphRAG context boundaries, Evidence Agent-only permissions, feature-flag compatibility,
safe execution metadata, endpoint behavior, and an optional live PostgreSQL graph round trip.
V6.5 adds deterministic in-memory PDF and DOCX fixtures plus TXT and Markdown bytes. Tests cover
all parsers, extension/MIME/signature routing, malformed and encrypted PDFs, explicit OCR-required
behavior, strict UTF-8, empty extraction, filename safety, upload bounds, multipart responses,
metadata and chunk provenance, normalized deduplication, unchanged plain-text ingestion, optional
graph degradation, real graph enrichment, retrieval/Evidence Agent compatibility, and PostgreSQL
JSONB provenance. All OpenAI embedding and structured-output boundaries remain mocked.
V7A adds network-free tests for perfect, partial, empty, duplicate, over-K, and negative retrieval;
dataset integrity; entity, relationship, path, and provenance metrics; invented-identity rejection;
all three retrieval modes; incompatible-case skips; non-secret configuration snapshots; JSON
serialization; comparison alignment; CLI output; and repeatability. No provider call is made.
V7B adds benchmark-integrity, finite-taxonomy, risk recall/precision, severity, controls,
governance, human oversight, architecture fit, over-engineering, claim support, citation,
abstention, specialist preservation, synthesis transparency, degraded/failure reporting,
three-mode comparison, optional-judge schema/security, CLI, and reproducibility coverage. The
judge and provider boundary are mocked.
V7C adds policy-outcome, reason-code, durable review, approval, rejection, bounded revision,
three-mode resume, invalid-transition, comment-injection isolation, retry/backoff, per-boundary
timeout, failure classification, telemetry accuracy/privacy, migration, and additive API coverage.

### PostgreSQL and pgvector integration tests

Create a dedicated test database with pgvector available. Its database name must contain `test`:

```bash
createdb enterprise_ai_test
export TEST_DATABASE_URL='postgresql+psycopg://enterprise_ai:local-password@localhost:5432/enterprise_ai_test'
pytest -m postgres
```

When `TEST_DATABASE_URL` is absent, PostgreSQL tests skip cleanly. When configured, the suite
refuses non-PostgreSQL URLs, maintenance or production-looking names, a database matching
`DATABASE_URL`, or a connection whose actual database differs from the named test database.

The opt-in suite is destructive only to the confirmed test schema: it verifies `alembic downgrade
base` and `upgrade head`, clears assessment and knowledge rows between tests, and checks PostgreSQL
version, pgvector extension availability, UUID/JSONB/TIMESTAMPTZ/vector storage, cosine nearest
neighbors, lifecycle persistence, and a grounded POST/GET assessment round trip with deterministic
embeddings and mocked OpenAI.

V6 also checks migration and graph-table creation plus UUID, JSONB, timezone-aware timestamp,
entity, mention, relationship, provenance, and bounded traversal behavior against the same guarded
test database. All fixtures are synthetic; no external knowledge dataset is required.

V6.5 adds a PostgreSQL round trip for file-origin document metadata, chunk page provenance, and
normalized deduplication without requiring a binary fixture or external dataset in the database.

V7C adds a PostgreSQL checkpoint/restart boundary with JSONB candidate state, UUID audit events,
TIMESTAMPTZ verification, and approval-driven finalization. It uses only synthetic fixtures.

Do not run multiple test processes against the same test database. Run only fast tests with:

```bash
pytest -m "not postgres"
```

## V7 evaluation scope boundary

V7A evaluates retrieval and provenance. V7B evaluates normalized final assessment quality and the
existing specialist/synthesis handoffs through deterministic fixtures, with an optional
schema-constrained judge. Neither stage changes runtime assessment behavior or claims production
assurance.

V7B adds no LangSmith, OpenTelemetry platform, vendor dashboard, persistent tracing, full
latency/token/cost analytics, SLO/SLA, retry framework, timeout framework, LangGraph interrupt or
resume, human-review queue, approval workflow, escalation engine, or runtime quality-gate
enforcement. V7C and V8A now provide internal reliability, observability, and infrastructure. MCP
remains deferred until a concrete interoperability use case exists.

The V6.5 ingestion limitations remain: scanned/image-only PDFs need OCR; file ingestion is
synchronous and memory-bounded; and legacy Word, spreadsheets, presentations, image understanding,
archive ingestion, web crawling, and external enterprise connectors are not implemented.
Production infrastructure—including Docker, CI/CD, authentication, authorization, malware
scanning, object storage, queues, hosted deployment, and frontend UI—remains deferred beyond V8A.
