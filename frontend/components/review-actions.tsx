"use client";

import { useState } from "react";

import { ApiError, api } from "@/lib/api/client";

export function ReviewActions({ assessmentId, onComplete }: Readonly<{ assessmentId: string; onComplete: () => void }>) {
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(action: "approve" | "reject" | "request-revision") {
    const label = action === "request-revision" ? "request revision" : action;
    if (!window.confirm(`Confirm ${label} for this assessment? This action is added to the audit history.`)) return;
    setBusy(action);
    setError(null);
    try {
      await api.review(assessmentId, action, comment);
      setComment("");
      onComplete();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The review action failed.");
    } finally {
      setBusy(null);
    }
  }

  return <div className="review-actions"><label htmlFor="review-comment">Reviewer comment <span>Optional, stored as untrusted audit text</span></label><textarea id="review-comment" maxLength={2000} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Summarize the decision or requested change." />{error && <p className="inline-error" role="alert">{error}</p>}<div className="button-row"><button className="button primary" disabled={busy !== null} onClick={() => void decide("approve")}>Approve</button><button className="button secondary" disabled={busy !== null} onClick={() => void decide("request-revision")}>Request revision</button><button className="button danger" disabled={busy !== null} onClick={() => void decide("reject")}>Reject</button></div></div>;
}
