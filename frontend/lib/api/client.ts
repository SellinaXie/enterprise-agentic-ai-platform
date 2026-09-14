import type {
  AssessmentInput,
  AssessmentListResponse,
  AssessmentResponse,
  EvaluationSummary,
  FileIngestionResponse,
  KnowledgeDocument,
  Principal,
  ReviewCandidate,
  ReviewRecord,
  RuntimeStatus,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "/backend";
const TOKEN_KEY = "enterprise-ai-access-token";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiResult<T> {
  data: T;
  requestId: string | null;
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
  else window.sessionStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const token = getAccessToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (!headers.has("X-Request-ID")) headers.set("X-Request-ID", crypto.randomUUID());
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  const requestId = response.headers.get("x-request-id");
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const error = payload?.error;
    throw new ApiError(
      error?.message ?? "The request could not be completed.",
      response.status,
      error?.code ?? "request_failed",
      requestId ?? payload?.request_id ?? null,
    );
  }
  return { data: payload as T, requestId };
}

export const api = {
  session: () => request<Principal>("/api/v1/session"),
  assessments: (params: { status?: string; offset?: number; limit?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set("status", params.status);
    if (params.offset) query.set("offset", String(params.offset));
    query.set("limit", String(params.limit ?? 25));
    return request<AssessmentListResponse>(`/api/v1/assessments?${query}`);
  },
  pendingReviews: (limit = 25) =>
    request<AssessmentListResponse>(`/api/v1/reviews/pending?limit=${limit}`),
  assessment: (id: string) => request<AssessmentResponse>(`/api/v1/assessments/${id}`),
  createAssessment: (input: AssessmentInput) =>
    request<AssessmentResponse>("/api/v1/assessments", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  runtimeStatus: (id: string) =>
    request<RuntimeStatus>(`/api/v1/assessments/${id}/runtime-status`),
  reviews: (id: string) =>
    request<ReviewRecord[]>(`/api/v1/assessments/${id}/reviews`),
  reviewCandidate: (id: string) =>
    request<ReviewCandidate>(`/api/v1/assessments/${id}/review-candidate`),
  review: (id: string, action: "approve" | "reject" | "request-revision", comment?: string) =>
    request(`/api/v1/assessments/${id}/reviews/${action}`, {
      method: "POST",
      body: JSON.stringify({ comment: comment?.trim() || null }),
    }),
  evaluation: () => request<EvaluationSummary>("/api/v1/evaluation/summary"),
  document: (id: string) => request<KnowledgeDocument>(`/api/v1/knowledge/documents/${id}`),
  upload: (form: FormData) =>
    request<FileIngestionResponse>("/api/v1/knowledge/files", { method: "POST", body: form }),
};
