# Enterprise AI Transformation Advisor

Production-minded V3 backend for grounded enterprise AI assessments. V3 preserves the V1
schema-constrained OpenAI assessment flow and V2 PostgreSQL application-state persistence, then
adds a logically separate pgvector knowledge layer for retrieval-augmented generation (RAG).

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

- `assessments` is V2 application state: validated requests, lifecycle status, structured result
  or safe failure, and timestamps.
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
result or safe failure, and lifecycle timestamps.

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
vectors, and mocked OpenAI clients. They cover normalization, chunking, batching and vector-shape
validation, repository persistence, retrieval query construction, filtering boundaries, source
metadata, controlled RAG context, zero-result fallback, knowledge APIs, grounding rules, and a
simulated end-to-end ingestion-to-persisted-assessment flow. No external dataset or provider network
call is required.

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

## V3 scope boundary

V3 is the knowledge and RAG baseline only. It does not activate the dormant LangGraph scaffold and
does not add ReAct loops, generic tool calling, agents, multi-agent orchestration, MCP, knowledge
graphs, GraphRAG, LangSmith instrumentation, UI, authentication, deployment, Docker, PDF parsing,
OCR, or a full evaluation framework. Those concerns remain deferred; do not infer them from the
presence of retrieval.
