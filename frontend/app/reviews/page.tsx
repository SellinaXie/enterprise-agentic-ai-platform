"use client";

import { useCallback, useEffect, useState } from "react";

import { AssessmentTable } from "@/components/assessment-table";
import { useAuth } from "@/components/auth-provider";
import { EmptyState, ErrorState, LoadingState, PageHeader, Panel } from "@/components/ui";
import { ApiError, api } from "@/lib/api/client";
import type { AssessmentListResponse } from "@/lib/api/types";

export default function ReviewsPage() {
  const auth = useAuth();
  const canReview = auth.hasRole("reviewer", "admin");
  const [data, setData] = useState<AssessmentListResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => { if (!canReview) { setLoading(false); return; } setLoading(true); setError(null); try { setData((await api.pendingReviews(50)).data); } catch (caught) { setError(caught instanceof ApiError ? caught : new ApiError("Unable to load reviews.", 0, "network_error", null)); } finally { setLoading(false); } }, [canReview]);
  useEffect(() => { void load(); }, [load]);
  return <><PageHeader eyebrow="Human-in-the-loop" title="Review queue" description="Inspect the persisted candidate, evidence, runtime decision, and prior history before recording an authenticated decision." />{auth.status !== "loading" && !canReview ? <Panel><ErrorState title="Reviewer access required" message="This queue is restricted to reviewer and admin roles. Hiding the navigation is a UX convenience; the backend also enforces this boundary." /></Panel> : <Panel>{loading ? <LoadingState label="Loading pending reviews" /> : error ? <ErrorState message={error.message} requestId={error.requestId} retry={() => void load()} /> : data?.items.length ? <AssessmentTable items={data.items} /> : <EmptyState title="Review queue is clear" description="No assessments currently require human intervention." />}</Panel>}</>;
}
