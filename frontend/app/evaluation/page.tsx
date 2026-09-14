"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { ErrorState, LoadingState, PageHeader, Panel, StatusBadge } from "@/components/ui";
import { ApiError, api } from "@/lib/api/client";
import type { EvaluationModeSummary, EvaluationSummary } from "@/lib/api/types";
import { formatMetric, titleCase } from "@/lib/format";

function MetricsTable({ reports }: Readonly<{ reports: EvaluationModeSummary[] }>) {
  const metrics = useMemo(() => Array.from(new Set(reports.flatMap((report) => Object.entries(report.aggregate_metrics).filter(([, value]) => typeof value === "number" || value === null).map(([key]) => key)))), [reports]);
  return <div className="table-scroll"><table className="metric-table"><thead><tr><th>Metric</th>{reports.map((report) => <th key={report.mode}>{titleCase(report.mode)}</th>)}</tr></thead><tbody>{metrics.map((metric) => <tr key={metric}><td>{titleCase(metric)}</td>{reports.map((report) => <td key={report.mode}>{formatMetric(report.aggregate_metrics[metric])}</td>)}</tr>)}</tbody></table></div>;
}

export default function EvaluationPage() {
  const [data, setData] = useState<EvaluationSummary | null>(null);
  const [view, setView] = useState<"v7a" | "v7b">("v7b");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const load = useCallback(async () => { setLoading(true); setError(null); try { setData((await api.evaluation()).data); } catch (caught) { setError(caught instanceof ApiError ? caught : new ApiError("Unable to run deterministic evaluation.", 0, "network_error", null)); } finally { setLoading(false); } }, []);
  useEffect(() => { void load(); }, [load]);
  const reports = view === "v7a" ? data?.v7a : data?.v7b;
  return <><PageHeader eyebrow="Evaluation harness" title="Architecture quality, measured transparently" description="Compare retrieval and assessment modes using version-controlled synthetic cases, explicit labels, and reproducible deterministic metrics." />{loading ? <Panel><LoadingState label="Running deterministic benchmark summaries" /></Panel> : error ? <Panel><ErrorState message={error.message} requestId={error.requestId} retry={() => void load()} /></Panel> : data && <div className="section-stack"><div className="callout warning"><strong>Synthetic benchmark—not production assurance</strong><p>{data.disclaimer}</p></div><Panel><div className="tabs" role="tablist" aria-label="Evaluation suite"><button className={view === "v7b" ? "active" : ""} onClick={() => setView("v7b")} role="tab" aria-selected={view === "v7b"}>V7B · Architecture & risk</button><button className={view === "v7a" ? "active" : ""} onClick={() => setView("v7a")} role="tab" aria-selected={view === "v7a"}>V7A · Retrieval</button></div><header className="panel-header"><div><span className="eyebrow">{view === "v7b" ? "Deterministic vs single-agent vs multi-agent" : "Vector vs graph vs hybrid"}</span><h2>{view === "v7b" ? "Architecture and governance quality" : "Retrieval and provenance quality"}</h2></div><StatusBadge value="synthetic" /></header>{reports && <MetricsTable reports={reports} />}</Panel><div className="grid three">{reports?.map((report) => <Panel key={report.mode} title={titleCase(report.mode)} eyebrow={`${report.evaluated_cases}/${report.total_cases} cases evaluated`}><p>Deterministic fixture result with no live provider calls.</p>{report.reproducibility_fingerprint && <div className="callout"><strong>Reproducibility fingerprint</strong><p><code>{report.reproducibility_fingerprint.slice(0, 20)}…</code></p></div>}<ul className="content-list">{report.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></Panel>)}</div><Panel title="How to interpret this comparison" eyebrow="Architecture judgment"><p>Higher coverage is useful only when claims remain grounded and the added orchestration is justified. The benchmark evaluates unsupported claims, abstention, precision, and over-engineering avoidance alongside recall. It does not assume that multi-agent execution should win.</p></Panel></div>}</>;
}
