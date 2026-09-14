"use client";

import { useState } from "react";

import { ApiError, api } from "@/lib/api/client";
import type { KnowledgeDocument, SourceReference } from "@/lib/api/types";

export function EvidenceList({ references }: Readonly<{ references: SourceReference[] }>) {
  const [documents, setDocuments] = useState<Record<string, KnowledgeDocument>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState<string | null>(null);

  async function loadDocument(documentId: string) {
    setLoading(documentId);
    try {
      const response = await api.document(documentId);
      setDocuments((current) => ({ ...current, [documentId]: response.data }));
    } catch (caught) {
      const message = caught instanceof ApiError ? caught.message : "Unable to load source details.";
      setErrors((current) => ({ ...current, [documentId]: message }));
    } finally {
      setLoading(null);
    }
  }

  return <div className="evidence-list">{references.map((reference) => {
    const document = documents[reference.document_id];
    return <article className="evidence-card" key={`${reference.document_id}-${reference.chunk_id}`}><header><div><span className="eyebrow">Source evidence</span><h3>{reference.document_title}</h3></div><span className="source-origin">Retrieved</span></header><dl><div><dt>Document</dt><dd><code>{reference.document_id}</code></dd></div><div><dt>Chunk</dt><dd><code>{reference.chunk_id}</code></dd></div></dl>{document ? <div className="evidence-excerpt"><strong>Stored source excerpt</strong><p>{document.content.slice(0, 1200)}</p>{document.content.length > 1200 && <small>Excerpt limited to 1,200 characters.</small>}</div> : <button className="text-button" disabled={loading === reference.document_id} onClick={() => void loadDocument(reference.document_id)}>{loading === reference.document_id ? "Loading source…" : "Inspect source metadata and excerpt"}</button>}{errors[reference.document_id] && <p className="inline-error">{errors[reference.document_id]}</p>}</article>;
  })}</div>;
}
