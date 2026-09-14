"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AssessmentTable } from "@/components/assessment-table";
import { EmptyState, ErrorState, LoadingState, PageHeader, Panel } from "@/components/ui";
import { ApiError, api } from "@/lib/api/client";
import type { AssessmentListResponse } from "@/lib/api/types";

export default function AssessmentsPage() {
  const [filter, setFilter] = useState("");
  const [data, setData] = useState<AssessmentListResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setData((await api.assessments({ status: filter || undefined, limit: 50 })).data); }
    catch (caught) { setError(caught instanceof ApiError ? caught : new ApiError("Unable to load assessments.", 0, "network_error", null)); }
    finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);

  return <><PageHeader eyebrow="Assessment portfolio" title="Enterprise AI initiatives" description="Inspect each initiative from business context through architecture, risk, runtime decision, and human review." actions={<Link className="button primary" href="/assessments/new">New assessment</Link>} /><Panel><div className="filter-row"><div className="field"><label htmlFor="status-filter">Lifecycle status</label><select id="status-filter" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="">All statuses</option><option value="pending">Pending</option><option value="processing">Processing</option><option value="pending_review">Pending review</option><option value="completed">Completed</option><option value="failed">Failed</option></select></div>{data && <span className="topbar-label">{data.total} matching assessment{data.total === 1 ? "" : "s"}</span>}</div>{loading ? <LoadingState label="Loading assessments" /> : error ? <ErrorState message={error.message} requestId={error.requestId} retry={() => void load()} /> : data?.items.length ? <AssessmentTable items={data.items} /> : <EmptyState title="No matching assessments" description="Adjust the lifecycle filter or create a new assessment." actionHref="/assessments/new" actionLabel="Create assessment" />}</Panel></>;
}
