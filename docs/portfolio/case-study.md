# Case study: governed enterprise AI assessment platform

## Problem

Enterprise teams often jump from a business idea to a chatbot or agent without deciding whether AI
is appropriate, what evidence grounds the design, which risks and controls matter, or who can
approve deployment. The project turns that ambiguous review into a structured, auditable workflow.

## Architecture judgment

The system keeps three execution patterns because no one pattern dominates: deterministic
generation for straightforward work, a bounded tool-using agent when iterative evidence search is
useful, and separated evidence/architecture/risk/synthesis specialists when independent judgment
earns the orchestration cost. All paths converge on one typed result, evaluation model, runtime
risk gate, human-review checkpoint, and audit trail.

PostgreSQL owns transactional state; pgvector adds semantic retrieval without a second data store.
GraphRAG is optional and falls back safely to vector evidence. Chat and embedding providers have
separate contracts because their capabilities and portability constraints differ. A single
read-only policy connector demonstrates enterprise ingestion without creating a broad integration
framework prematurely.

## Controls

The platform enforces bounded tools and loops, source provenance, schema-constrained outputs,
unsupported-claim checks, safe abstention, centralized gate decisions, authenticated RBAC review,
content-free telemetry, production configuration validation, request correlation, migrations,
health/readiness, and explicit backup/restore procedures. No chain-of-thought is stored.

## Verification and outcome

Network-free tests cover domain logic, APIs, provider adapters, evaluations, governance, identity,
connector behavior, and frontend workflows. A dedicated real-PostgreSQL suite validates UUID,
JSONB, TIMESTAMPTZ, pgvector, migrations, lifecycle persistence, graph integrity, and API round
trips. CI builds both containers and runs Compose smoke tests.

The result is a deployable reference architecture and interview-ready system-design artifact, not
a certified product. Synthetic benchmark scores show repeatability and relative behavior only.
There is no measured production model quality, cloud SLO, full multi-tenancy, enterprise
provisioning, or regulatory assurance.
