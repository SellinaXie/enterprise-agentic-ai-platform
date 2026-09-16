export interface DemoStage {
  id: string;
  shortLabel: string;
  eyebrow: string;
  title: string;
  summary: string;
  outcome: string;
  details: Array<{ label: string; value: string }>;
}

export const demoStages: DemoStage[] = [
  {
    id: "architecture",
    shortLabel: "Architecture",
    eyebrow: "Decision intelligence",
    title: "Earn complexity from the use case",
    summary:
      "The platform compares deterministic, single-agent, and multi-agent execution before recommending a bounded architecture.",
    outcome: "Multi-agent with human approval",
    details: [
      { label: "Business context", value: "Synthetic retail-bank lending support" },
      { label: "Decision boundary", value: "Recommendation only; no autonomous credit decision" },
      { label: "Why specialists", value: "Independent architecture, risk, governance, and evidence review" },
    ],
  },
  {
    id: "evidence",
    shortLabel: "Evidence",
    eyebrow: "Grounded retrieval",
    title: "Trace claims to controlled evidence",
    summary:
      "Vector retrieval and bounded GraphRAG surface relevant policy passages with document, chunk, entity, and relationship provenance.",
    outcome: "3 synthetic sources grounded",
    details: [
      { label: "POL-014 · chunk 03", value: "Human approval is required before adverse-action recommendations." },
      { label: "STD-008 · chunk 11", value: "Customer PII must remain within approved processing boundaries." },
      { label: "GRAPH path", value: "Lending Assistant → uses → Customer Data → governed by → AI Policy" },
    ],
  },
  {
    id: "risk",
    shortLabel: "Risk",
    eyebrow: "Structured risk analysis",
    title: "Make risk and uncertainty explicit",
    summary:
      "Finite taxonomies keep findings comparable while unsupported claims and missing evidence are surfaced instead of hidden.",
    outcome: "High risk · review required",
    details: [
      { label: "Privacy · high", value: "Sensitive customer data requires minimization and access controls." },
      { label: "Explainability · high", value: "Recommendations need traceable factors and reviewable evidence." },
      { label: "Model risk · medium", value: "Drift, hallucination, and policy-version changes require monitoring." },
    ],
  },
  {
    id: "evaluation",
    shortLabel: "Evaluation",
    eyebrow: "Evidence-based comparison",
    title: "Compare quality without declaring a universal winner",
    summary:
      "Deterministic fixtures compare retrieval and execution modes across groundedness, architecture fit, risk precision, control coverage, abstention, and unsupported claims.",
    outcome: "Tradeoffs visible · no production claim",
    details: [
      { label: "V7A retrieval", value: "Vector, graph, and hybrid evidence quality with provenance and negative-query checks" },
      { label: "V7B assessment", value: "Deterministic, single-agent, and multi-agent architecture/risk judgment" },
      { label: "Assurance boundary", value: "Synthetic benchmark performance is not live-provider or production assurance" },
    ],
  },
  {
    id: "governance",
    shortLabel: "Governance",
    eyebrow: "Runtime control plane",
    title: "Turn recommendations into enforceable controls",
    summary:
      "The runtime gate evaluates risk, provenance, degraded execution, specialist availability, and mitigation coverage before completion.",
    outcome: "require_human_review",
    details: [
      { label: "Reason code", value: "HIGH_RISK_REVIEW_REQUIRED" },
      { label: "Control coverage", value: "RBAC, least privilege, retrieval grounding, audit logging" },
      { label: "Safe degradation", value: "Provider or retrieval failure cannot silently become approval" },
    ],
  },
  {
    id: "review",
    shortLabel: "HITL",
    eyebrow: "Authenticated human review",
    title: "Pause the workflow without exposing authority",
    summary:
      "This public example shows the review checkpoint, but approve, reject, and revision actions remain available only to authenticated reviewer/admin roles.",
    outcome: "Synthetic checkpoint paused",
    details: [
      { label: "Candidate", value: "Validated and persisted; not yet a final result" },
      { label: "Public demo authority", value: "None — controls are illustrative and non-operational" },
      { label: "Audit identity", value: "Real actions derive subject, role, issuer, and request ID from JWT claims" },
    ],
  },
  {
    id: "operations",
    shortLabel: "Operations",
    eyebrow: "Production foundation",
    title: "Observe outcomes without storing private reasoning",
    summary:
      "Health, latency, retries, timeouts, degradation, review state, and provider-reported usage are observable through privacy-safe telemetry.",
    outcome: "Healthy · bounded · auditable",
    details: [
      { label: "Execution", value: "Multi-agent · 4 specialists · deterministic fan-in" },
      { label: "Reliability", value: "2 retries · explicit timeouts · safe failure categories" },
      { label: "Privacy boundary", value: "No prompts, documents, embeddings, secrets, or chain-of-thought" },
    ],
  },
];

export const architectureJourney = [
  { version: "V0–V2", label: "Foundation", detail: "Typed API, structured assessment, PostgreSQL lifecycle" },
  { version: "V3–V4", label: "Grounding", detail: "pgvector RAG and bounded single-agent tools" },
  { version: "V5–V6.5", label: "Orchestration", detail: "Specialists, GraphRAG, enterprise document ingestion" },
  { version: "V7", label: "Assurance", detail: "Retrieval and quality evaluation, runtime governance, HITL" },
  { version: "V8", label: "Product", detail: "Production foundation, identity, UI, deployment boundaries" },
];
