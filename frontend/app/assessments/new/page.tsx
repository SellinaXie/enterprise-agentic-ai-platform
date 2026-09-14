"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { PageHeader, Panel } from "@/components/ui";
import { ApiError, api } from "@/lib/api/client";
import type { AssessmentInput, FileIngestionResponse } from "@/lib/api/types";

const initialForm: AssessmentInput = { company_name: "", industry: "", business_problem: "", desired_outcome: "", pain_points: [], constraints: [], organization_description: null, current_process: null, additional_context: null };

export default function NewAssessmentPage() {
  const router = useRouter();
  const [form, setForm] = useState(initialForm);
  const [painPoints, setPainPoints] = useState("");
  const [constraints, setConstraints] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [enrichGraph, setEnrichGraph] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<FileIngestionResponse | null>(null);
  const [uploadError, setUploadError] = useState<ApiError | null>(null);

  function update(name: keyof AssessmentInput, value: string) { setForm((current) => ({ ...current, [name]: value || null })); }
  function lines(value: string) { return value.split("\n").map((item) => item.trim()).filter(Boolean); }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await api.createAssessment({ ...form, pain_points: lines(painPoints), constraints: lines(constraints) });
      router.push(`/assessments/${response.data.assessment_id}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("Unable to create the assessment.", 0, "network_error", null));
    } finally { setSubmitting(false); }
  }

  async function upload() {
    if (!file) return;
    setUploading(true); setUploadError(null); setUploadResult(null);
    const body = new FormData(); body.set("file", file); if (fileTitle.trim()) body.set("title", fileTitle.trim()); body.set("enrich_graph", String(enrichGraph));
    try { setUploadResult((await api.upload(body)).data); }
    catch (caught) { setUploadError(caught instanceof ApiError ? caught : new ApiError("Unable to upload the document.", 0, "network_error", null)); }
    finally { setUploading(false); }
  }

  return <><PageHeader eyebrow="New initiative" title="Assess an enterprise AI opportunity" description="Provide the business context the platform needs to recommend the simplest defensible architecture and surface governance requirements." /><div className="section-stack"><Panel title="Supporting evidence" eyebrow="Optional first step"><div className="upload-zone"><div className="form-grid"><div className="field"><label htmlFor="evidence-file">Enterprise document <span>PDF, DOCX, TXT, or Markdown</span></label><input id="evidence-file" type="file" accept=".pdf,.docx,.txt,.md,text/plain,text/markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></div><div className="field"><label htmlFor="file-title">Display title <span>Optional</span></label><input id="file-title" value={fileTitle} maxLength={300} onChange={(event) => setFileTitle(event.target.value)} placeholder="Human Oversight Policy" /></div><div className="field full"><label><input type="checkbox" checked={enrichGraph} onChange={(event) => setEnrichGraph(event.target.checked)} /> Enrich the knowledge graph after ingestion</label></div></div><div className="button-row"><button className="button secondary" type="button" disabled={!file || uploading} onClick={() => void upload()}>{uploading ? "Uploading and parsing…" : "Upload evidence"}</button><small>Maximum size is controlled by the backend. Scanned PDFs return an OCR-required error.</small></div>{uploadResult && <div className="callout"><strong>{uploadResult.duplicate ? "Existing document reused" : "Evidence ready"}</strong><p>{uploadResult.document.title} · {uploadResult.chunk_count} chunk{uploadResult.chunk_count === 1 ? "" : "s"}</p></div>}{uploadError && <p className="inline-error" role="alert">{uploadError.message}{uploadError.requestId ? ` · Request ID: ${uploadError.requestId}` : ""}</p>}</div></Panel><Panel title="Business context" eyebrow="Assessment input"><form className="form-grid" onSubmit={(event) => void submit(event)}><div className="field"><label htmlFor="company">Organization</label><input id="company" required maxLength={200} value={form.company_name} onChange={(event) => update("company_name", event.target.value)} placeholder="Northstar Services" /></div><div className="field"><label htmlFor="industry">Industry</label><input id="industry" required maxLength={120} value={form.industry} onChange={(event) => update("industry", event.target.value)} placeholder="Financial services" /></div><div className="field full"><label htmlFor="org-description">Organization context <span>Optional</span></label><textarea id="org-description" maxLength={2000} value={form.organization_description ?? ""} onChange={(event) => update("organization_description", event.target.value)} placeholder="Describe the operating environment, users, and relevant constraints." /></div><div className="field full"><label htmlFor="problem">Business problem</label><textarea id="problem" required maxLength={2000} value={form.business_problem} onChange={(event) => update("business_problem", event.target.value)} placeholder="What decision, process, or service needs improvement?" /></div><div className="field full"><label htmlFor="process">Current process <span>Optional</span></label><textarea id="process" maxLength={4000} value={form.current_process ?? ""} onChange={(event) => update("current_process", event.target.value)} placeholder="How does the work happen today?" /></div><div className="field"><label htmlFor="pain-points">Pain points <span>One per line</span></label><textarea id="pain-points" value={painPoints} onChange={(event) => setPainPoints(event.target.value)} placeholder={"Manual policy lookup\nInconsistent review quality"} /></div><div className="field"><label htmlFor="constraints">Constraints <span>One per line</span></label><textarea id="constraints" value={constraints} onChange={(event) => setConstraints(event.target.value)} placeholder={"Human approval required\nData must remain private"} /></div><div className="field full"><label htmlFor="outcome">Desired outcome</label><textarea id="outcome" required maxLength={2000} value={form.desired_outcome} onChange={(event) => update("desired_outcome", event.target.value)} placeholder="Describe a measurable, operational outcome." /></div><div className="field full"><label htmlFor="additional">Additional context <span>Optional</span></label><textarea id="additional" maxLength={4000} value={form.additional_context ?? ""} onChange={(event) => update("additional_context", event.target.value)} /></div><div className="field full"><div className="form-note">Execution mode, retrieval, GraphRAG, and runtime governance are selected by trusted backend configuration. This interface does not override policy or orchestration controls.</div></div>{error && <div className="field full"><p className="inline-error" role="alert">{error.message}{error.requestId ? ` · Request ID: ${error.requestId}` : ""}</p></div>}<div className="field full"><div className="button-row"><button className="button primary" disabled={submitting}>{submitting ? "Running governed assessment…" : "Start assessment"}</button><span className="topbar-label">The API runs synchronously; no private reasoning is streamed.</span></div></div></form></Panel></div></>;
}
