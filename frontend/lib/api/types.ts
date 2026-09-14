export type Role = "analyst" | "reviewer" | "admin";
export type AssessmentStatus =
  | "pending"
  | "processing"
  | "pending_review"
  | "completed"
  | "failed";
export type RuntimeDecision =
  | "auto_complete"
  | "complete_with_warning"
  | "require_human_review"
  | "block_and_escalate";

export interface Principal {
  subject: string;
  email: string | null;
  display_name: string | null;
  roles: Role[];
  issuer: string | null;
}

export interface AssessmentInput {
  company_name: string;
  organization_description?: string | null;
  industry: string;
  business_problem: string;
  current_process?: string | null;
  pain_points: string[];
  desired_outcome: string;
  constraints: string[];
  additional_context?: string | null;
}

export interface AssessmentRisk {
  category: string;
  description: string;
  severity: "low" | "medium" | "high" | "critical";
  mitigation: string;
}

export interface SourceReference {
  document_id: string;
  chunk_id: string;
  document_title: string;
}

export interface AssessmentResult {
  executive_summary: string;
  problem_analysis: {
    core_problem: string;
    current_process_weaknesses: string[];
    key_bottlenecks: string[];
  };
  ai_suitability: { level: string; rationale: string };
  recommended_use_cases: Array<{
    name: string;
    description: string;
    expected_business_value: string;
    complexity: string;
    priority: string;
  }>;
  recommended_solution: { pattern: string; description: string; rationale: string };
  risks: AssessmentRisk[];
  human_oversight: {
    review_recommended: boolean;
    decisions_requiring_review: string[];
    rationale: string;
  };
  next_steps: Array<{ priority: number; action: string; rationale: string }>;
  assumptions: string[];
  information_gaps: string[];
  external_evidence_status: string;
  source_references: SourceReference[];
}

export interface AssessmentResponse {
  assessment_id: string;
  status: AssessmentStatus;
  input: AssessmentInput;
  result: AssessmentResult | null;
  execution: Record<string, unknown> | null;
  error: { code: string; message: string } | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface AssessmentListItem {
  assessment_id: string;
  company_name: string;
  industry: string;
  business_problem: string;
  status: AssessmentStatus;
  execution_mode: string | null;
  created_by_subject: string | null;
  runtime_decision: RuntimeDecision | null;
  risk_level: string | null;
  reason_codes: string[];
  review_status: string | null;
  request_id: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface AssessmentListResponse {
  items: AssessmentListItem[];
  total: number;
  offset: number;
  limit: number;
  status_counts: Record<string, number>;
  runtime_decision_counts: Record<string, number>;
  review_status_counts: Record<string, number>;
}

export interface RuntimeEvent {
  timestamp: string;
  request_id: string | null;
  event_type: string;
  component: string;
  status: string;
  duration_ms: number | null;
  reason_code: string | null;
}

export interface OperationalTelemetry {
  request_id: string | null;
  execution_mode: string;
  execution_health: string;
  total_duration_ms: number;
  execution_duration_ms: number;
  human_wait_duration_ms: number | null;
  retrieval_duration_ms: number | null;
  synthesis_duration_ms: number | null;
  model_call_count: number | null;
  model_call_durations_ms: number[];
  embedding_call_count: number | null;
  tool_call_count: number;
  graph_retrieval_used: boolean;
  vector_retrieval_used: boolean;
  specialist_durations_ms: Record<string, number | null>;
  retry_count: number;
  timeout_count: number;
  degraded_state_count: number;
  human_review_status: string;
  termination_reason: string;
  token_usage: {
    input_tokens: number | null;
    output_tokens: number | null;
    total_tokens: number | null;
  } | null;
  estimated_cost: number | null;
  estimated_cost_currency: string | null;
  events: RuntimeEvent[];
}

export interface RuntimeStatus {
  assessment_id: string;
  gate_result: {
    decision: RuntimeDecision;
    risk_level: string;
    reason_codes: string[];
    review_required: boolean;
    blocked: boolean;
  };
  review_status: string;
  revision_count: number;
  max_revisions: number;
  telemetry: OperationalTelemetry;
}

export interface ReviewCandidate {
  assessment_id: string;
  result: AssessmentResult;
  execution: Record<string, unknown> | null;
  gate_result: RuntimeStatus["gate_result"];
  review_status: string;
  telemetry: OperationalTelemetry;
  revision_count: number;
  max_revisions: number;
}

export interface ReviewRecord {
  review_id: string;
  assessment_id: string;
  action: string;
  previous_status: string;
  new_status: string;
  reviewer_id: string | null;
  reviewer_subject: string | null;
  reviewer_email: string | null;
  reviewer_role: string | null;
  reviewer_issuer: string | null;
  request_id: string | null;
  comment: string | null;
  reason_codes: string[];
  revision_number: number;
  created_at: string;
}

export interface EvaluationModeSummary {
  mode: string;
  synthetic: boolean;
  total_cases: number;
  evaluated_cases: number;
  aggregate_metrics: Record<string, unknown>;
  warnings: string[];
  reproducibility_fingerprint: string | null;
}

export interface EvaluationSummary {
  v7a: EvaluationModeSummary[];
  v7b: EvaluationModeSummary[];
  disclaimer: string;
}

export interface KnowledgeDocument {
  document_id: string;
  title: string;
  source_type: string;
  source_uri: string | null;
  external_id: string | null;
  content: string;
  metadata: Record<string, unknown>;
  content_hash: string;
  created_at: string;
  updated_at: string;
}

export interface FileIngestionResponse {
  document: KnowledgeDocument;
  chunk_count: number;
  duplicate: boolean;
  file: {
    filename: string;
    file_format: string;
    media_type: string;
    size_bytes: number;
  };
  graph_enrichment: Record<string, unknown> | null;
}
