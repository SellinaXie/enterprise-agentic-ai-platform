# Enterprise AI Transformation Advisor

Production-minded V2 backend for assessing where AI or automation can create value in an
enterprise business process.

V2 preserves the synchronous, schema-constrained OpenAI assessment flow from V1 and adds
PostgreSQL-backed application state. It records the validated request, lifecycle status,
structured result or safe failure, and UTC timestamps. PostgreSQL is not a knowledge or RAG
database in this version.

## Architecture

```text
FastAPI → Assessment Service → Assessment Repository → PostgreSQL
                    └───────→ OpenAI Service
```

- FastAPI owns HTTP validation, routing, and safe error responses.
- `AssessmentService` owns lifecycle orchestration and transaction boundaries.
- `AssessmentRepository` owns SQLAlchemy persistence operations.
- The OpenAI adapter owns Responses API access and schema-constrained parsing.
- Pydantic HTTP models, persistence-neutral domain records, and ORM models remain separate.

The stack is synchronous end to end because the existing route and OpenAI client are
synchronous. Each lifecycle milestone is committed intentionally: `pending`, `processing`,
then `completed` or `failed`. This preserves a durable failure record when generation fails.

## Requirements

- Python 3.12 or newer
- PostgreSQL
- `pip`
- An OpenAI API key for assessment generation

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

Create a PostgreSQL database and dedicated application account, then set `DATABASE_URL` in
`.env`. The SQLAlchemy URL uses Psycopg 3, for example:

```dotenv
DATABASE_URL=postgresql+psycopg://enterprise_ai:local-password@localhost:5432/enterprise_ai
```

Also set `OPENAI_API_KEY`. Never commit `.env`. The application does not log the database URL,
credentials, private assessment payloads, or raw prompts.

Apply the canonical schema migration:

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
`http://127.0.0.1:8000/docs`.

`GET /health` remains a process liveness check and does not open a database connection.
Assessment endpoints return a controlled `503` when persistence is not configured or available.

## API

### Create and persist an assessment

```bash
curl -X POST http://127.0.0.1:8000/api/v1/assessments \
  -H 'Content-Type: application/json' \
  -d '{
    "company_name": "Example Bank",
    "organization_description": "A regional retail and commercial bank",
    "industry": "Banking",
    "business_problem": "Manual loan review takes too long",
    "current_process": "Analysts manually gather documents and assess risk",
    "pain_points": ["Repeated document collection"],
    "desired_outcome": "Reduce processing time while preserving compliance",
    "constraints": ["Final credit decisions require human approval"]
  }'
```

A successful synchronous response remains `200 OK` and includes persisted state:

```json
{
  "assessment_id": "5ab59db6-8a53-4d49-a0e0-4d861984a150",
  "status": "completed",
  "input": {
    "company_name": "Example Bank",
    "industry": "Banking",
    "business_problem": "Manual loan review takes too long",
    "desired_outcome": "Reduce processing time while preserving compliance"
  },
  "result": {
    "executive_summary": "..."
  },
  "error": null,
  "created_at": "2026-09-09T13:00:00Z",
  "updated_at": "2026-09-09T13:00:01Z",
  "completed_at": "2026-09-09T13:00:01Z"
}
```

The abbreviated `input` and `result` objects above represent the complete validated request and
existing structured assessment schemas.

### Retrieve an assessment

```bash
curl http://127.0.0.1:8000/api/v1/assessments/5ab59db6-8a53-4d49-a0e0-4d861984a150
```

`GET /api/v1/assessments/{assessment_id}` returns the stored request, result or safe failure,
and lifecycle timestamps. Unknown IDs return `404`; invalid UUIDs return `422`.

If generation fails, the row remains in PostgreSQL with `status = failed`, no fabricated result,
and only a safe error code and public message.

## Database schema

The `assessments` table contains:

- UUID primary key compatible with existing assessment IDs.
- Status constrained to `pending`, `processing`, `completed`, or `failed`.
- Queryable `company_name`, `industry`, and `business_problem` columns.
- Complete request and result snapshots in PostgreSQL JSONB.
- Safe nullable error code/message fields.
- Timezone-aware creation, update, and completion timestamps.
- Indexes for status and creation time.

Alembic is the production schema authority. `Base.metadata.create_all()` is used only to build
isolated SQLite test schemas.

## Testing

```bash
pytest
ruff check .
ruff format --check .
python -m compileall app tests
python -m pip check
alembic history
```

Tests mock the OpenAI layer and never make a real provider request. Repository and API tests use
an isolated SQLite database per test for speed and independence. The default suite also renders
the Alembic migration with the PostgreSQL dialect and asserts that UUID, JSONB, constraints, and
indexes are present.

### PostgreSQL integration tests

Create a dedicated test database that is separate from the application database. The database
name must contain `test`; `enterprise_ai_test` is one example:

```bash
createdb enterprise_ai_test
export TEST_DATABASE_URL='postgresql+psycopg://enterprise_ai:local-password@localhost:5432/enterprise_ai_test'
pytest -m postgres
```

The `postgres` tests are skipped cleanly when `TEST_DATABASE_URL` is unset. When it is set, the
suite refuses non-PostgreSQL URLs, database names without `test`, PostgreSQL maintenance
databases, production-looking database names, and any database with the same host, port, and name
as `DATABASE_URL`.

The PostgreSQL suite is intentionally destructive to the V2 schema in the confirmed test
database: it runs `alembic downgrade base` followed by `alembic upgrade head`, and deletes rows
from `assessments` before and after each test. Never set `TEST_DATABASE_URL` to a production,
staging, development, or shared application database. Do not run multiple copies of this suite
concurrently against the same test database.

Run only the fast SQLite-backed tests with:

```bash
pytest -m "not postgres"
```

The live PostgreSQL checks cover the connection and server version, migration state and table
creation, native UUID/JSONB/TIMESTAMPTZ behavior, repository lifecycle persistence, safe failed
state persistence, and the POST/GET API flow with a mocked OpenAI client. All assessment inputs
and results come from deterministic local synthetic fixtures; no external dataset is required.

## V2 scope

V2 adds relational application-state persistence only. It intentionally does not add pgvector,
embeddings, document or chunk models, retrieval, RAG, active LangGraph orchestration, tools,
agents, MCP, knowledge graphs, authentication, background jobs, Docker, or CI/CD.

Document ingestion and vector retrieval remain explicitly deferred to V3 and will use separate
document/chunk/embedding models rather than being mixed into assessment persistence.
