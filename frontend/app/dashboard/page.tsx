"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AssessmentTable } from "@/components/assessment-table";
import { BarList, EmptyState, ErrorState, LoadingState, MetricCard, PageHeader, Panel } from "@/components/ui";
import { ApiError, api } from "@/lib/api/client";
import type { AssessmentListResponse } from "@/lib/api/types";

export default function DashboardPage() {
  const [data, setData] = useState<AssessmentListResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData((await api.assessments({ limit: 50 })).data);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("Unable to reach the API.", 0, "network_error", null));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const executionModes = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const item of data?.items ?? []) {
      const mode = item.execution_mode ?? "not_available";
      counts[mode] = (counts[mode] ?? 0) + 1;
    }
    return Object.entries(counts).map(([label, value]) => ({ label, value, tone: "information" }));
  }, [data]);

  return (
    <>
      <PageHeader eyebrow="Executive overview" title="AI architecture decisions, with evidence" description="Track architecture recommendations, risk decisions, human interventions, and execution health from one governed workspace." actions={<Link className="button primary" href="/assessments/new">New assessment</Link>} />
      {loading ? <Panel><LoadingState label="Loading portfolio state" /></Panel> : error ? <Panel><ErrorState message={error.message} requestId={error.requestId} retry={() => void load()} /></Panel> : data && (
        <div className="section-stack">
          <div className="metric-grid">
            <MetricCard label="Total assessments" value={Object.values(data.status_counts).reduce((sum, value) => sum + value, 0)} note="Authoritative database total" tone="information" />
            <MetricCard label="Pending human review" value={data.review_status_counts.pending ?? 0} note="Reviewer action required" tone="review" />
            <MetricCard label="Blocked or escalated" value={data.runtime_decision_counts.block_and_escalate ?? 0} note="Runtime gate decision" tone="critical" />
            <MetricCard label="Completed" value={data.status_counts.completed ?? 0} note="Includes reviewed approvals" tone="positive" />
          </div>
          <div className="grid two">
            <Panel title="Runtime decisions" eyebrow="Governance distribution"><BarList items={Object.entries(data.runtime_decision_counts).map(([label, value]) => ({ label, value, tone: label === "block_and_escalate" ? "critical" : label === "complete_with_warning" ? "warning" : "" }))} /></Panel>
            <Panel title="Execution modes" eyebrow="Current page"><BarList items={executionModes} /></Panel>
          </div>
          <Panel title="Recent assessments" eyebrow="Latest activity" action={<Link href="/assessments">View all →</Link>}>
            {data.items.length ? <AssessmentTable items={data.items.slice(0, 8)} /> : <EmptyState title="No assessments yet" description="Create the first architecture and risk assessment to populate this workspace." actionHref="/assessments/new" actionLabel="Create assessment" />}
          </Panel>
        </div>
      )}
    </>
  );
}
