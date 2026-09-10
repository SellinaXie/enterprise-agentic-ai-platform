# Enterprise AI Transformation Advisor

Production-minded V6 backend for grounded enterprise AI assessments. V6 preserves the complete
V1-V5 behavior and adds an opt-in relational knowledge graph, source-grounded extraction, bounded
graph traversal, and hybrid vector-plus-graph GraphRAG in the existing PostgreSQL database.

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
the Responses API structured-output parser; the small configured retry applies to provider or
schema failure, not an open-ended self-repair loop. Prompts and raw provider conversations are not
passed between agents.

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
SPECIALIST_RETRY_LIMIT=1
```

- `text-embedding-3-small` is requested at 1,536 dimensions. The typed setting, ORM vector type,
  and immutable V3 migration agree on this schema dimension. The OpenAI embeddings API supports
  a requested `dimensions` value for `text-embedding-3` models.
- Chunk size and overlap are measured in characters. The deterministic chunker prefers paragraph,
  line, then word boundaries. A 1,200/200 baseline keeps context units readable while retaining
  boundary continuity without adding a tokenizer dependency.
- Retrieval uses cosine similarity and filters results below 0.35 before returning at most five.
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
- `SPECIALIST_RETRY_LIMIT=1` permits one retry after the initial schema-constrained specialist
  request. It does not create an agent-directed repair loop.
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
`GET /api/v1/knowledge/documents/{document_id}` returns the normalized stored document.

V3 intentionally accepts plain text only. It does not add file upload, PDF parsing, or OCR.

After ingesting a document, opt in to V6 and extract its graph from the already stored chunks:

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/knowledge/documents/DOCUMENT_UUID/graph
```

This synchronous endpoint is idempotent for deterministically identical entities, mentions, and
source-grounded relationships. The document must already exist; it does not upload, parse, or
replace source content.

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

`POST /api/v1/assessments` retains its V2 persistence lifecycle:

```text
pending → processing → completed | failed
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

Do not run multiple test processes against the same test database. Run only fast tests with:

```bash
pytest -m "not postgres"
```

## V6 scope boundary

V6 is a controlled, source-grounded relational graph and GraphRAG increment—not a general graph or
autonomous-agent platform. Implemented now: PostgreSQL graph tables, constrained per-chunk
extraction, conservative entity resolution, provenance, bounded traversal, hybrid retrieval,
GraphRAG context, the Evidence Agent graph tool, safe fallbacks, settings, API enrichment, tests,
and documentation.

Still planned or explicitly out of scope: PDF/DOCX parsing, OCR, browser or file upload, external
datasets, Neo4j, Cypher, arbitrary graph queries, graph visualization UI, evaluation frameworks,
LangSmith, MCP, Docker, CI/CD, authentication, deployment, asynchronous extraction jobs, generalized
agent memory, and human-in-the-loop pause/resume infrastructure. V6.5 has not been started.
