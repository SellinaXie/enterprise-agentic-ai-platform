"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { EvidenceList } from "@/components/evidence-list";
import { ReviewActions } from "@/components/review-actions";
import { RuntimeDecisionCard } from "@/components/runtime-decision";
import { DefinitionList, EmptyState, ErrorState, LoadingState, MetricCard, PageHeader, Panel, StatusBadge } from "@/components/ui";
import { ApiError, api } from "@/lib/api/client";
import type { AssessmentResponse, AssessmentResult, ReviewCandidate, ReviewRecord, RuntimeStatus } from "@/lib/api/types";
import { formatDate, formatDuration, titleCase } from "@/lib/format";

export default function AssessmentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const auth = useAuth();
  const canReview = auth.hasRole("reviewer", "admin");
  const [assessment, setAssessment] = useState<AssessmentResponse | null>(null);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [candidate, setCandidate] = useState<ReviewCandidate | null>(null);
  const [reviews, setReviews] = useState<ReviewRecord[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const assessmentResponse = await api.assessment(id);
      setAssessment(assessmentResponse.data);
      const [runtimeResponse, reviewResponse, candidateResponse] = await Promise.allSettled([
        api.runtimeStatus(id),
        canReview ? api.reviews(id) : Promise.reject(new Error("role_not_permitted")),
        canReview && assessmentResponse.data.status === "pending_review" ? api.reviewCandidate(id) : Promise.reject(new Error("candidate_not_required")),
      ]);
      setRuntime(runtimeResponse.status === "fulfilled" ? runtimeResponse.value.data : null);
      setReviews(reviewResponse.status === "fulfilled" ? reviewResponse.value.data : []);
      setCandidate(candidateResponse.status === "fulfilled" ? candidateResponse.value.data : null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("Unable to load the assessment.", 0, "network_error", null));
    } finally { setLoading(false); }
  }, [canReview, id]);

  useEffect(() => { void load(); }, [load]);

  if (loading) return <Panel><LoadingState label="Loading assessment workspace" /></Panel>;
  if (error) return <Panel><ErrorState message={error.message} requestId={error.requestId} retry={() => void load()} /></Panel>;
  if (!assessment) return null;

  const result: AssessmentResult | null = assessment.result ?? candidate?.result ?? null;
  const telemetry = runtime?.telemetry ?? candidate?.telemetry ?? null;

  return <><PageHeader eyebrow="Assessment workspace" title={assessment.input.company_name} description={assessment.input.business_problem} actions={<><StatusBadge value={assessment.status} /><Link className="button secondary" href="/assessments">Back to portfolio</Link></>} />{runtime && <RuntimeDecisionCard runtime={runtime} />}{!runtime && <div className="callout"><strong>Runtime governance state is not available</strong><p>This assessment may predate the runtime gate or the gate may be disabled. No frontend decision has been inferred.</p></div>}<div className="section-stack" style={{ marginTop: 18 }}><div className="grid two"><Panel title="Initiative context" eyebrow="Submitted input"><DefinitionList items={[{ label: "Industry", value: assessment.input.industry }, { label: "Desired outcome", value: assessment.input.desired_outcome }, { label: "Current process", value: assessment.input.current_process ?? "Not provided" }, { label: "Created", value: formatDate(assessment.created_at) }, { label: "Execution mode", value: <StatusBadge value={telemetry?.execution_mode ?? (assessment.execution?.execution_mode as string | undefined)} /> }]} /></Panel><Panel title="Assessment posture" eyebrow="Structured decision">{result ? <DefinitionList items={[{ label: "AI suitability", value: <StatusBadge value={result.ai_suitability.level} /> }, { label: "Architecture pattern", value: titleCase(result.recommended_solution.pattern) }, { label: "External evidence", value: titleCase(result.external_evidence_status) }, { label: "Human oversight", value: result.human_oversight.review_recommended ? "Recommended" : "Not required by this assessment" }, { label: "Updated", value: formatDate(assessment.updated_at) }]} /> : <EmptyState title="Result is not publicly available" description={assessment.status === "pending_review" ? "The validated candidate remains behind the reviewer authorization boundary until a human decision is recorded." : assessment.error?.message ?? "The assessment has not completed."} />}</Panel></div>{result && <><Panel title="Executive assessment" eyebrow="Decision summary"><p style={{ color: "var(--ink)", fontSize: ".95rem" }}>{result.executive_summary}</p><div className="grid two"><div className="callout"><strong>Core problem</strong><p>{result.problem_analysis.core_problem}</p></div><div className="callout"><strong>AI suitability</strong><p>{result.ai_suitability.rationale}</p></div></div></Panel><div className="grid two"><Panel title="Recommended architecture" eyebrow="Simplest defensible pattern"><StatusBadge value={result.recommended_solution.pattern} /><p style={{ marginTop: 14 }}>{result.recommended_solution.description}</p><div className="callout"><strong>Why this fits</strong><p>{result.recommended_solution.rationale}</p></div>{result.recommended_use_cases.length > 0 && <><h3 style={{ marginTop: 18 }}>Prioritized use cases</h3><ul className="content-list">{result.recommended_use_cases.map((item) => <li key={item.name}><strong>{item.name}</strong> — {item.description} <StatusBadge value={item.complexity} /></li>)}</ul></>}</Panel><Panel title="Governance requirements" eyebrow="Human authority and gaps"><div className="callout"><strong>{result.human_oversight.review_recommended ? "Human review recommended" : "No mandatory review identified"}</strong><p>{result.human_oversight.rationale}</p></div>{result.human_oversight.decisions_requiring_review.length > 0 && <><h3 style={{ marginTop: 18 }}>Decisions requiring review</h3><ul className="content-list">{result.human_oversight.decisions_requiring_review.map((item) => <li key={item}>{item}</li>)}</ul></>}{result.information_gaps.length > 0 && <><h3 style={{ marginTop: 18 }}>Information gaps</h3><ul className="content-list">{result.information_gaps.map((item) => <li key={item}>{item}</li>)}</ul></>}</Panel></div><Panel title="Risk and control coverage" eyebrow="Governance analysis"><div className="risk-grid">{result.risks.map((risk, index) => <article className="risk-card" key={`${risk.category}-${index}`}><header><h3>{titleCase(risk.category)}</h3><StatusBadge value={risk.severity} /></header><p>{risk.description}</p><footer><strong>Recommended control</strong><br />{risk.mitigation}</footer></article>)}</div></Panel><Panel title="Evidence and provenance" eyebrow={`${result.source_references.length} attributed source${result.source_references.length === 1 ? "" : "s"}`}>{result.source_references.length ? <EvidenceList references={result.source_references} /> : <EmptyState title="No external evidence cited" description="The assessment was produced from submitted business context only, or no retrieved source survived citation validation." />}</Panel><Panel title="Recommended next steps" eyebrow="Action plan"><ol className="content-list">{[...result.next_steps].sort((a, b) => a.priority - b.priority).map((step) => <li key={`${step.priority}-${step.action}`}><strong>{step.action}</strong> — {step.rationale}</li>)}</ol></Panel></>}{telemetry && <><div className="metric-grid"><MetricCard label="Total latency" value={formatDuration(telemetry.total_duration_ms)} note="Model execution only" tone="information" /><MetricCard label="Model calls" value={telemetry.model_call_count ?? "Not available"} note="Provider-reported boundary" /><MetricCard label="Tool calls" value={telemetry.tool_call_count} note={`${telemetry.retry_count} retries · ${telemetry.timeout_count} timeouts`} /><MetricCard label="Estimated cost" value={telemetry.estimated_cost === null ? "Not available" : `${telemetry.estimated_cost_currency ?? "USD"} ${telemetry.estimated_cost.toFixed(4)}`} note="Only when pricing is configured" /></div><Panel title="Safe execution trace" eyebrow="Operational metadata only">{telemetry.events.length ? <ol className="timeline">{telemetry.events.map((event, index) => <li key={`${event.timestamp}-${event.event_type}-${index}`}><time>{formatDate(event.timestamp)}</time><div><strong>{titleCase(event.event_type)}</strong><p>{titleCase(event.component)} · {titleCase(event.status)}{event.reason_code ? ` · ${titleCase(event.reason_code)}` : ""}</p></div><span>{formatDuration(event.duration_ms)}</span></li>)}</ol> : <EmptyState title="No trace events" description="This execution did not persist safe runtime trace events." />}</Panel></>}{assessment.status === "pending_review" && canReview && <Panel title="Human decision" eyebrow="Reviewer authorization required"><ReviewActions assessmentId={assessment.assessment_id} onComplete={() => void load()} /></Panel>}{assessment.status === "pending_review" && !canReview && <Panel><EmptyState title="Awaiting authorized review" description="The candidate and decision controls are restricted to reviewer and admin roles. Backend authorization remains authoritative." /></Panel>}{canReview && <Panel title="Audit history" eyebrow="Append-only review events">{reviews.length ? <ol className="timeline">{reviews.map((review) => <li key={review.review_id}><time>{formatDate(review.created_at)}</time><div><strong>{titleCase(review.action)}</strong><p>{review.reviewer_email ?? review.reviewer_subject ?? "System"} · revision {review.revision_number}{review.comment ? ` · ${review.comment}` : ""}</p></div><StatusBadge value={review.new_status} /></li>)}</ol> : <EmptyState title="No review events" description="No human-review transition has been recorded for this assessment." />}</Panel>}{telemetry?.request_id && <p className="topbar-label">Troubleshooting request ID: <code>{telemetry.request_id}</code></p>}</div></>;
}
