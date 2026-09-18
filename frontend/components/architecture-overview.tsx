import Link from "next/link";

import { Icon } from "./icons";

const flowSteps = [
  { step: "Ingest & ground", detail: "Bounded APIs accept PDF, DOCX, UTF-8 text, and Markdown; content is normalized, chunked with provenance, embedded, and optionally added to the knowledge graph. Original upload bytes are not persisted." },
  { step: "Retrieve evidence", detail: "Vector RAG finds semantically relevant chunks while bounded GraphRAG adds entity relationships and impact paths, both attributable to a source document and chunk." },
  { step: "Choose execution mode", detail: "A deterministic flow handles straightforward cases; a single agent may use two read-only knowledge tools; a multi-agent graph separates evidence, architecture, risk/governance, and synthesis roles." },
  { step: "Synthesize & validate", detail: "All paths converge on one typed assessment contract. Citation sanitization removes invented or duplicate provenance before anything is persisted." },
  { step: "Evaluate & instrument", detail: "Deterministic, version-controlled fixtures score retrieval and assessment quality outside the production request path; safe operational telemetry exports over OTLP/HTTP." },
  { step: "Apply the runtime risk gate", detail: "A centralized, deterministic gate decides whether a result may complete, should carry a warning, requires human review, or must be blocked and escalated." },
  { step: "Human review & audit", detail: "Reviewers authenticate with signed JWTs; RBAC governs who may decide. Decisions are appended to a durable, attributed audit history rather than overwriting it." },
];

const componentGroups = [
  {
    title: "Data and grounding",
    eyebrow: "Why these exist",
    items: [
      "PostgreSQL is the transactional system of record for assessment lifecycle, knowledge chunks, graph entities, runtime checkpoints, and review events — one database keeps them transactionally consistent.",
      "pgvector adds embedding storage and cosine-similarity search without a separate vector database, appropriate at the current scale.",
      "RAG grounds assessments in enterprise evidence instead of relying on a model's general knowledge, with source identifiers that make claims inspectable.",
      "The knowledge graph / GraphRAG represents typed relationships so bounded traversal can expose dependencies and impact chains similarity search alone would miss.",
    ],
  },
  {
    title: "Execution and quality",
    eyebrow: "Why these exist",
    items: [
      "LangGraph provides explicit state, routing, and deterministic fan-in, so orchestration and failure paths stay inspectable rather than relying on an unconstrained supervisor agent.",
      "Single-agent mode is used when one reasoning loop benefits from selective tool use; multi-agent mode is reserved for cases where independent evidence, architecture, and governance analysis earns its extra coordination cost.",
      "The evaluation harness gives repeatable, version-controlled comparisons across retrieval, provenance, architecture fit, risk coverage, groundedness, and abstention.",
      "Runtime governance and human-in-the-loop review make sure a technically successful model response is never automatically treated as an approved enterprise decision.",
    ],
  },
  {
    title: "Portability, access, and operations",
    eyebrow: "Why these exist",
    items: [
      "Provider abstraction keeps vendor SDKs inside adapters, with separate contracts for chat models and embeddings so a reasoning provider can change without invalidating the vector index.",
      "OIDC/JWKS, JWT, and RBAC establish a stateless identity boundary: signed tokens are checked for algorithm, signature, issuer, audience, expiry, subject, and role before any protected action.",
      "Docker and CI make the production-like topology repeatable — linting, typechecking, deterministic regressions, a real PostgreSQL/pgvector integration suite, and health/readiness checks run on every push.",
    ],
  },
];

const limitations = [
  "The deployment manifest is present, but no measured cloud SLO exists yet.",
  "Full tenant isolation, tenant-aware authorization, quotas, and data partitioning are not present.",
  "OCR and image-only PDF ingestion are not supported; neither are Excel or PowerPoint ingestion.",
  "Only one generic HTTPS policy-repository connector exists; Google Drive, SharePoint, ticketing, messaging, and GRC connectors are not implemented.",
  "OIDC/JWKS token verification is present, but browser authorization-code login, SCIM provisioning, and IdP lifecycle administration are not.",
  "There is no external observability SaaS, managed alerting, or production incident integration.",
  "Live-provider architecture, risk, and retrieval quality has not been benchmarked; current results use deterministic synthetic fixtures, not production assurance.",
];

export function ArchitectureOverview() {
  return (
    <div className="demo-page">
      <header className="demo-nav">
        <Link className="demo-brand" href="/" aria-label="Enterprise AI Risk Intelligence">
          <span className="brand-mark"><Icon name="shield" width="22" height="22" /></span>
          <span><strong>AI Risk Intelligence</strong><small>Architecture overview</small></span>
        </Link>
        <div className="demo-nav-actions">
          <span className="demo-synthetic-pill">Read-only · no backend call</span>
          <Link className="button secondary compact" href="/demo">Guided demo</Link>
        </div>
      </header>

      <main id="main-content">
        <section className="showcase-hero">
          <span className="eyebrow">System design</span>
          <h1>How this platform is built, and why.</h1>
          <p>
            The platform turns enterprise business context and internal knowledge into structured,
            evidence-aware architecture assessments. It is not a generic chatbot: its output is a
            validated assessment covering solution architecture, integrations, risk, governance,
            human oversight, and information gaps — using deterministic, single-agent, or
            multi-agent execution only where the problem earns that complexity.
          </p>
        </section>

        <section className="showcase-section" aria-labelledby="flow-title">
          <div className="showcase-section-heading">
            <span className="eyebrow">End-to-end flow</span>
            <h2 id="flow-title">How one decision moves through the system</h2>
          </div>
          <ol className="timeline">
            {flowSteps.map((item, index) => (
              <li key={item.step}>
                <time>{String(index + 1).padStart(2, "0")}</time>
                <div><strong>{item.step}</strong><p>{item.detail}</p></div>
              </li>
            ))}
          </ol>
        </section>

        <section className="showcase-section" aria-labelledby="components-title">
          <div className="showcase-section-heading">
            <span className="eyebrow">Design rationale</span>
            <h2 id="components-title">Why the major components exist</h2>
          </div>
          <div className="grid three">
            {componentGroups.map((group) => (
              <div className="panel" key={group.title}>
                <div className="panel-header"><div><span className="eyebrow">{group.eyebrow}</span><h2>{group.title}</h2></div></div>
                <ul className="content-list">
                  {group.items.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ))}
          </div>
        </section>

        <section className="showcase-section" aria-labelledby="tradeoffs-title">
          <div className="showcase-section-heading">
            <span className="eyebrow">Judgment</span>
            <h2 id="tradeoffs-title">Complexity is earned, not assumed</h2>
          </div>
          <div className="callout">
            <strong>The deterministic path is a first-class option, not a fallback.</strong>
            <p>
              A fixed transformation or simple rule can be safer, cheaper, and easier to audit than
              an agent. Single-agent execution earns its place when bounded tool choice materially
              improves context gathering; multi-agent execution is justified only when independent
              evidence, architecture, and governance analysis exposes disagreement that a single
              pass would miss — more agents also mean more latency, cost, and failure surface.
              Producing more risks or controls is not valuable if they are irrelevant or
              unsupported, so the platform is evaluated on precision as well as coverage, and
              rewards appropriate abstention.
            </p>
          </div>
        </section>

        <section className="showcase-section" aria-labelledby="limits-title">
          <div className="showcase-section-heading">
            <span className="eyebrow">Honest scope</span>
            <h2 id="limits-title">Current limitations</h2>
          </div>
          <div className="panel">
            <ul className="content-list">
              {limitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </section>
      </main>

      <footer className="demo-footer">
        <span>Enterprise AI Architecture &amp; Risk Intelligence Platform</span>
        <a href="https://github.com/SellinaXie/enterprise-agentic-ai-platform/blob/main/docs/architecture/overview.md">Read the full architecture document</a>
      </footer>
    </div>
  );
}
