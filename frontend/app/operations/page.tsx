"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState, PageHeader, Panel, StatusBadge } from "@/components/ui";
import { ApiError, api } from "@/lib/api/client";
import type { AssessmentListItem, RuntimeStatus } from "@/lib/api/types";
import { formatDuration, titleCase, truncate } from "@/lib/format";

interface RuntimeRow { assessment: AssessmentListItem; runtime: RuntimeStatus; }

export default function OperationsPage() {
  const [rows, setRows] = useState<RuntimeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const load = useCallback(async () => { setLoading(true); setError(null); try { const assessments = (await api.assessments({ limit: 25 })).data.items; const statuses = await Promise.allSettled(assessments.map((item) => api.runtimeStatus(item.assessment_id))); setRows(statuses.flatMap((status, index) => status.status === "fulfilled" ? [{ assessment: assessments[index], runtime: status.value.data }] : [])); } catch (caught) { setError(caught instanceof ApiError ? caught : new ApiError("Unable to load operational telemetry.", 0, "network_error", null)); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  return <><PageHeader eyebrow="Runtime operations" title="Reliability without sensitive payloads" description="Inspect bounded latency, usage, retry, timeout, and degradation signals. Prompts, documents, embeddings, tokens, and private reasoning are excluded." /><Panel>{loading ? <LoadingState label="Loading runtime telemetry" /> : error ? <ErrorState message={error.message} requestId={error.requestId} retry={() => void load()} /> : rows.length ? <div className="table-scroll"><table><thead><tr><th>Assessment</th><th>Mode</th><th>Health</th><th>Latency</th><th>Calls</th><th>Reliability</th><th>Cost</th></tr></thead><tbody>{rows.map(({ assessment, runtime }) => <tr key={assessment.assessment_id}><td><div className="table-primary"><Link href={`/assessments/${assessment.assessment_id}`}><strong>{assessment.company_name}</strong></Link><span>{truncate(assessment.business_problem, 55)}</span>{runtime.telemetry.request_id && <small>Request {runtime.telemetry.request_id}</small>}</div></td><td>{titleCase(runtime.telemetry.execution_mode)}</td><td><StatusBadge value={runtime.telemetry.execution_health} /></td><td>{formatDuration(runtime.telemetry.total_duration_ms)}<br /><small>Human wait: {formatDuration(runtime.telemetry.human_wait_duration_ms)}</small></td><td>{runtime.telemetry.model_call_count ?? "N/A"} model<br />{runtime.telemetry.embedding_call_count ?? "N/A"} embedding<br />{runtime.telemetry.tool_call_count} tool</td><td>{runtime.telemetry.retry_count} retries<br />{runtime.telemetry.timeout_count} timeouts<br />{runtime.telemetry.degraded_state_count} degraded</td><td>{runtime.telemetry.estimated_cost === null ? "Not available" : `${runtime.telemetry.estimated_cost_currency ?? "USD"} ${runtime.telemetry.estimated_cost.toFixed(4)}`}</td></tr>)}</tbody></table></div> : <EmptyState title="No runtime telemetry yet" description="Runtime records appear after assessments execute with the governance layer enabled." actionHref="/assessments/new" actionLabel="Create assessment" />}</Panel><div className="callout" style={{ marginTop: 18 }}><strong>Operational boundary</strong><p>Human-review wait time remains separate from model execution latency. Missing provider counters are shown as “Not available,” never converted to zero.</p></div></>;
}
