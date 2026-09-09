# Enterprise AI Transformation Advisor

Production-minded V4 backend for grounded enterprise AI assessments. V4 preserves the V1
schema-constrained OpenAI assessment flow, V2 PostgreSQL application-state persistence, and V3
pgvector RAG layer, then adds an optional controlled single-agent LangGraph workflow.

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

### Deterministic versus agentic execution

```dotenv
AGENTIC_WORKFLOW_ENABLED=false
# Existing V3 deterministic request/retrieval/synthesis behavior

AGENTIC_WORKFLOW_ENABLED=true
# V4 LangGraph single-agent reason/act/observe/synthesize behavior
```

The default is `false`. `RAG_ENABLED` continues to control retrieval in deterministic mode. In
agentic mode the agent chooses whether to invoke retrieval through its tool registry. Both modes
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
tool exists. V4 has exactly one agent and adds no supervisor, worker agents, multi-agent
orchestration, MCP, LangSmith, knowledge graph, or GraphRAG capability.

### Safe execution trace

Agentic assessments persist one compact JSONB execution summary with `execution_mode`,
`steps_used`, unique `tools_used`, `termination_reason`, and timestamped safe events. Events record
the transition and outcome (for example, tool requested/completed/failed), not model reasoning,
full prompts, tool arguments, secrets, embeddings, or complete documents. Deterministic V3 results
leave this optional field empty.

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
  safe failure, timestamps, and an optional compact V4 agent execution summary.
- `knowledge_documents` and `knowledge_chunks` are V3 retrieval knowledge: normalized source
  text, provenance metadata, deterministic chunks, embeddings, and chunk metadata.

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

AGENTIC_WORKFLOW_ENABLED=false
AGENT_MAX_STEPS=5
AGENT_MAX_TOOL_CALLS=5
LANGGRAPH_RECURSION_LIMIT=25
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
result or safe failure, lifecycle timestamps, and optional safe V4 execution metadata.

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
provider network call is required.

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

Do not run multiple test processes against the same test database. Run only fast tests with:

```bash
pytest -m "not postgres"
```

## V4 scope boundary

V4 activates the prior LangGraph scaffold only for the optional controlled single-agent workflow.
It is not a general agent platform and does not add multiple agents, a supervisor/worker pattern,
multi-agent orchestration, arbitrary tools, MCP, knowledge graphs, GraphRAG, LangSmith, an eval
framework, UI, authentication, deployment, Docker, file parsing, or OCR. Those concerns remain
outside V4; V5 has not been started.
