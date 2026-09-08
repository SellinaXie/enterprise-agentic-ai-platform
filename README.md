# Enterprise AI Transformation Advisor

Production-minded V1 backend for assessing where AI or automation can create
value in an enterprise business process.

V1 accepts validated discovery context, makes one synchronous OpenAI Responses
API call, constrains the model output with a Pydantic schema, validates the
result again at the service boundary, and returns a completed assessment. It
does not use LangGraph orchestration, agents, retrieval, or persistence yet.

## Requirements

- Python 3.12 or newer
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

Set `OPENAI_API_KEY` in `.env`. The application and `GET /health` work without
a key, but `POST /api/v1/assessments` returns a controlled `503` response until
one is configured. Never commit `.env`.

`OPENAI_MODEL` selects the model centrally. The default is `gpt-4.1-mini`.
Provider-side response storage is disabled by default through
`OPENAI_STORE_RESPONSES=false`.

## Run the API

```bash
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`, with interactive OpenAPI
documentation at `http://127.0.0.1:8000/docs`.

Useful endpoints:

- `GET /health`
- `POST /api/v1/assessments`

## Example assessment

```bash
curl -X POST http://127.0.0.1:8000/api/v1/assessments \
  -H 'Content-Type: application/json' \
  -d '{
    "company_name": "Example Bank",
    "organization_description": "A regional retail and commercial bank",
    "industry": "Banking",
    "business_problem": "Manual loan review takes too long",
    "current_process": "Analysts manually gather documents and assess risk",
    "pain_points": [
      "Repeated document collection",
      "Inconsistent review summaries"
    ],
    "desired_outcome": "Reduce processing time while preserving compliance",
    "constraints": ["Final credit decisions require human approval"]
  }'
```

The generated content varies, but every successful response follows this shape:

```json
{
  "assessment_id": "5ab59db6-8a53-4d49-a0e0-4d861984a150",
  "status": "completed",
  "result": {
    "executive_summary": "...",
    "problem_analysis": {
      "core_problem": "...",
      "current_process_weaknesses": ["..."],
      "key_bottlenecks": ["..."]
    },
    "ai_suitability": {
      "level": "high",
      "rationale": "..."
    },
    "recommended_use_cases": [
      {
        "name": "...",
        "description": "...",
        "expected_business_value": "...",
        "complexity": "medium",
        "priority": "high"
      }
    ],
    "recommended_solution": {
      "pattern": "llm_assisted_workflow",
      "description": "...",
      "rationale": "..."
    },
    "risks": [
      {
        "category": "compliance",
        "description": "...",
        "severity": "high",
        "mitigation": "..."
      }
    ],
    "human_oversight": {
      "review_recommended": true,
      "decisions_requiring_review": ["..."],
      "rationale": "..."
    },
    "next_steps": [
      {"priority": 1, "action": "...", "rationale": "..."}
    ],
    "assumptions": ["..."],
    "information_gaps": ["..."]
  }
}
```

## Run checks

```bash
pytest
ruff check .
ruff format --check .
python -m compileall app tests
python -m pip check
```

Tests inject or mock the assessment generator and never make a real OpenAI API
request.

## Current architecture

- `app/api`: HTTP routes, exception responses, and dependency wiring.
- `app/core`: environment configuration, application errors, and JSON logging.
- `app/schemas`: validated API contracts and the structured LLM output schema.
- `app/models`: constrained domain enums.
- `app/services`: prompt construction, assessment orchestration, and OpenAI access.
- `app/graph`: inactive LangGraph scaffold reserved for a later version.
- `app/agents`: future agent definitions and orchestration components.
- `app/tools`: future structured tool/function implementations.
- `app/rag`: future retrieval and knowledge-source components.
- `app/evaluation`: future tracing and evaluation support.
- `tests`: API, prompt, schema, failure-path, and health tests.

The route delegates to the assessment service. The service builds provider-neutral
prompt context and calls an injected generator. The OpenAI implementation alone
knows about the Responses API and schema-constrained parsing.

## V1 boundaries

V1 intentionally does not add PostgreSQL, pgvector, embeddings, RAG, active
LangGraph execution, tools, multiple agents, MCP, LangSmith, authentication,
Docker, or CI/CD.
