# Contributing

Use Python 3.12 and the Node version pinned by the frontend container. Keep changes small, typed,
network-free by default, and compatible with the existing architecture. New AI modes, providers,
connectors, tools, data stores, or authorization concepts require an explicit decision record and
are not assumed improvements.

Before opening a change:

```bash
pytest -m "not postgres"
ruff check .
ruff format --check .
python -m compileall app tests scripts

cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Use `TEST_DATABASE_URL` only for the guarded dedicated PostgreSQL suite. Do not point tests at a
production database. Never commit secrets, generated builds, local databases, dumps, coverage, or
environment files. Update tests and relevant architecture/operations documentation with behavior
changes. Preserve safe error messages, provenance, RBAC, content-free telemetry, and the no
chain-of-thought-storage boundary.
