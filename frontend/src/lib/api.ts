/**
 * Typed API client for FastAPI backend endpoints.
 */

export interface AffectedGR {
  label: string;
  gr_number_canonical?: string | null;
  relevance_note?: string | null;
  corpus_excerpt?: string | null;
}

export interface ConflictPair {
  draft_clause: string;
  corpus_excerpt: string;
  gr_label: string;
  gr_number_canonical?: string | null;
  gr_number_original?: string | null;
  gr_number_normalized?: string | null;
  relevance_note?: string | null;
  // Per-conflict structured English fields
  per_conflict_explanation?: string | null;
  draft_proposes?: string | null;
  existing_gr_provides?: string | null;
  conflict_type?: "override" | "overlap" | "inconsistency" | null;
  recommendation?: string | null;
}

export interface RuleSignal {
  signal_type: string;
  value: string;
  note?: string;
  matched_gr_id?: number | null;
}

export interface RetrievalQualityInfo {
  passed: boolean;
  result_count: number;
  above_threshold_count: number;
  max_score: number;
  min_score_threshold: number;
  chunk_hits: number;
  graph_degraded: boolean;
  graph_skipped: boolean;
  warnings: string[];
}

export interface ConflictFinding {
  conflicting: boolean;
  explanation: string;
  conflicting_clauses: string[];
  affected_grs: AffectedGR[];
  confidence: number;
  cross_departmental?: boolean;
  supersession_detected?: boolean;
  degraded?: boolean;
  degradation_reasons?: string[];
  retrieval_quality?: RetrievalQualityInfo | null;
  rule_signals?: RuleSignal[];
  draft_clauses_detected?: string[];
  conflict_pairs?: ConflictPair[];
}

export interface GlossaryFinding {
  text_found: string;
  context_snippet: string;
  canonical_term: string;
  reason: string;
  confidence: number;
}

export interface GlossaryCheckSection {
  status: "ok" | "unavailable" | "error";
  reason?: string | null;
  findings: GlossaryFinding[];
}

export interface ConflictCheckSection {
  status: "ok" | "error";
  reason?: string | null;
  result?: ConflictFinding | null;
}

export interface DraftAnalysisResponse {
  conflict_check: ConflictCheckSection;
  glossary_check: GlossaryCheckSection;
  template_check: TemplateCheckSection;
}

export interface AnalysisFinding {
  id: string;
  severity: SeverityLevel;
  category: string;
  summary: string;
  matched_text?: string;
  location?: string;
  description?: string;
  analysis?: string;
  recommendation?: string;
  line_number?: number | null;
  char_offset?: number | null;
  line_range?: [number, number];
}

export type SeverityLevel = "high" | "medium" | "low";

export interface TemplateViolation {
  violation_type: "missing" | "misordered";
  section_id: string;
  section_label: string;
  severity: SeverityLevel;
  description: string;
  expected_after?: string | null;
  found_at_line?: number | null;
  char_offset?: number | null;
}

export interface TemplateCheckSection {
  status: "ok";
  accuracy_score: number;
  total_required_sections: number;
  sections_correct: number;
  sections_present: number;
  violations: TemplateViolation[];
  findings: AnalysisFinding[];
  section_positions?: Record<string, number>;
}

export interface StoreSyncHealth {
  in_sync: boolean;
  warnings?: string[];
  postgres_documents?: number;
  neo4j_gr_nodes?: number | null;
  chunk_count?: number;
}

export interface EmbeddingsHealth {
  ok: boolean;
  count: number;
  total_documents: number;
  coverage: number;
}

export interface HealthStatus {
  status: "ok" | "degraded";
  db: boolean;
  neo4j: boolean;
  neo4j_error?: string | null;
  embeddings?: EmbeddingsHealth;
  store_sync?: StoreSyncHealth;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  "http://localhost:8000";

/**
 * Health check — Postgres, Neo4j, and embedding coverage.
 */
export async function checkHealth(): Promise<HealthStatus> {
  try {
    const res = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      headers: { "Content-Type": "application/json" },
    });
    if (!res.ok) {
      throw new ApiError(res.status, `Health check failed with status ${res.status}`);
    }
    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(0, err instanceof Error ? err.message : "Backend unreachable");
  }
}

/**
 * Perform conflict detection for draft GR text
 */
export async function checkConflict(
  draftText: string,
  opts?: { topK?: number; hops?: number }
): Promise<ConflictFinding> {
  const payload = {
    draft_text: draftText,
    top_k: opts?.topK ?? 15,
    hops: opts?.hops ?? 1,
  };

  try {
    const res = await fetch(`${API_BASE_URL}/reasoning/conflict`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let errDetail = `API error ${res.status}`;
      try {
        const body = await res.json();
        if (body.detail) errDetail = body.detail;
        else if (body.error) errDetail = body.error;
      } catch {
        // Fallback to HTTP status text if JSON parse fails
      }
      throw new ApiError(res.status, errDetail);
    }

    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(0, err instanceof Error ? err.message : "Network error calling reasoning API");
  }
}

export interface AnalysisProgressEvent {
  step: "read" | "extract" | "corpus" | "detect" | "analyse";
  label: string;
  detail: string;
  count?: number;
}

/**
 * Stream real-time analysis progress metrics via SSE.
 */
export async function analyzeDraftStream(
  draftText: string,
  onProgress: (event: AnalysisProgressEvent) => void,
  opts?: { topK?: number; hops?: number; grDocumentId?: number; actor?: string },
): Promise<DraftAnalysisResponse> {
  const payload: Record<string, unknown> = {
    draft_text: draftText,
    top_k: opts?.topK ?? 15,
    hops: opts?.hops ?? 1,
  };
  if (opts?.grDocumentId != null) {
    payload.gr_document_id = opts.grDocumentId;
  }
  if (opts?.actor) {
    payload.actor = opts.actor;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/reasoning/analyze-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      return analyzeDraft(draftText, opts);
    }

    if (!res.body) {
      return analyzeDraft(draftText, opts);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalResult: DraftAnalysisResponse | null = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";

      for (const chunk of parts) {
        if (!chunk.trim()) continue;
        const lines = chunk.split("\n");
        let eventType = "";
        let dataStr = "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.replace("event:", "").trim();
          } else if (line.startsWith("data:")) {
            dataStr = line.replace("data:", "").trim();
          }
        }

        if (dataStr) {
          try {
            const parsed = JSON.parse(dataStr);
            if (eventType === "progress") {
              onProgress(parsed as AnalysisProgressEvent);
            } else if (eventType === "complete") {
              finalResult = parsed as DraftAnalysisResponse;
            }
          } catch {
            // ignore chunk issue
          }
        }
      }
    }

    if (finalResult) return finalResult;
    return analyzeDraft(draftText, opts);
  } catch {
    return analyzeDraft(draftText, opts);
  }
}

/**
 * Run conflict + glossary terminology checks in parallel (partial per-section success).
 */
export async function analyzeDraft(
  draftText: string,
  opts?: { topK?: number; hops?: number; grDocumentId?: number; actor?: string },
): Promise<DraftAnalysisResponse> {
  const payload: Record<string, unknown> = {
    draft_text: draftText,
    top_k: opts?.topK ?? 15,
    hops: opts?.hops ?? 1,
  };
  if (opts?.grDocumentId != null) {
    payload.gr_document_id = opts.grDocumentId;
  }
  if (opts?.actor) {
    payload.actor = opts.actor;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/reasoning/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      let errDetail = `API error ${res.status}`;
      try {
        const body = await res.json();
        if (body.detail) errDetail = body.detail;
        else if (body.error) errDetail = body.error;
      } catch {
        // ignore
      }
      throw new ApiError(res.status, errDetail);
    }

    return await res.json();
  } catch (err: unknown) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(0, err instanceof Error ? err.message : "Network error calling analyze API");
  }
}

export type DraftStatus = "draft" | "ready_for_approval" | "approved";

export interface DraftSummary {
  id: number;
  filename: string;
  status: DraftStatus;
  version_number: number;
  full_text: string;
}

export interface VersionHistoryItem {
  id: number;
  gr_document_id: number;
  version_number: number;
  full_text: string;
  actor: string;
  lines_added: number;
  lines_deleted: number;
  chars_added: number;
  chars_deleted: number;
  raw_diff?: string | null;
  created_at?: string | null;
}

export interface DraftSaveResponse {
  draft: DraftSummary;
  template_check: TemplateCheckSection;
  glossary_check: GlossaryCheckSection;
}

export interface ClauseDiffResult {
  /** Clauses that did not exist in the previous version */
  added: string[];
  /** Clauses at the same position index but with changed content */
  modified: string[];
  /** Clauses whose content is byte-for-byte identical to the previous version */
  unchanged: string[];
  /** True when added or modified is non-empty */
  has_changes: boolean;
}

export interface DraftRecheckResponse extends DraftSaveResponse {
  conflict_check: ConflictCheckSection;
  /** Clause-level diff — only added/modified clauses need re-checking */
  clause_diff: ClauseDiffResult;
}

const DEFAULT_ACTOR =
  (typeof localStorage !== "undefined" &&
    localStorage.getItem("gr_actor")) ||
  "anonymous officer";

function draftHeaders(actor?: string): HeadersInit {
  const resolved = actor?.trim() || DEFAULT_ACTOR;
  return {
    "Content-Type": "application/json",
    "X-Actor": resolved,
  };
}

export async function createDraft(
  fullText: string,
  filename: string,
  actor?: string,
): Promise<DraftSummary> {
  const res = await fetch(`${API_BASE_URL}/drafts`, {
    method: "POST",
    headers: draftHeaders(actor),
    body: JSON.stringify({
      full_text: fullText,
      filename,
      actor: actor || DEFAULT_ACTOR,
    }),
  });
  if (!res.ok) {
    let errDetail = `API error ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) errDetail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, errDetail);
  }
  return await res.json();
}

export async function saveDraft(
  draftId: number,
  fullText: string,
  actor?: string,
): Promise<DraftSaveResponse> {
  const res = await fetch(`${API_BASE_URL}/drafts/${draftId}/save`, {
    method: "POST",
    headers: draftHeaders(actor),
    body: JSON.stringify({
      full_text: fullText,
      actor: actor || DEFAULT_ACTOR,
    }),
  });
  if (!res.ok) {
    let errDetail = `API error ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) errDetail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, errDetail);
  }
  return await res.json();
}

export async function saveAndRecheckDraft(
  draftId: number,
  fullText: string,
  actor?: string,
): Promise<DraftRecheckResponse> {
  const res = await fetch(`${API_BASE_URL}/drafts/${draftId}/save-and-recheck`, {
    method: "POST",
    headers: draftHeaders(actor),
    body: JSON.stringify({
      full_text: fullText,
      actor: actor || DEFAULT_ACTOR,
    }),
  });
  if (!res.ok) {
    let errDetail = `API error ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) errDetail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, errDetail);
  }
  return await res.json();
}

export async function getDraftVersions(
  draftId: number
): Promise<VersionHistoryItem[]> {
  const res = await fetch(`${API_BASE_URL}/drafts/${draftId}/versions`, {
    headers: draftHeaders(),
  });
  if (!res.ok) {
    let errDetail = `API error ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) errDetail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, errDetail);
  }
  return await res.json();
}

export interface ChatHistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export type ChatMessageStatus = "ok" | "unavailable" | "no_document" | "error";

export interface ChatMessageResponse {
  status: ChatMessageStatus;
  reply?: string | null;
  reason?: string | null;
}

export async function sendChatMessage(payload: {
  message: string;
  draftText: string;
  history: ChatHistoryMessage[];
  sessionId: string;
}): Promise<ChatMessageResponse> {
  try {
    const res = await fetch(`${API_BASE_URL}/chat/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: payload.message,
        draft_text: payload.draftText,
        history: payload.history,
        session_id: payload.sessionId,
      }),
    });

    if (!res.ok) {
      return {
        status: "error",
        reason: "http_error",
        reply: `Chat request failed (${res.status}).`,
      };
    }

    return await res.json();
  } catch (err: unknown) {
    return {
      status: "error",
      reason: "network_error",
      reply:
        err instanceof Error
          ? err.message
          : "Could not reach the chat service.",
    };
  }
}

export interface GRComment {
  id: number;
  gr_document_id: number;
  parent_id?: number | null;
  user_name: string;
  user_role: string;
  user_department: string;
  comment_type: "question" | "answer" | "review_comment" | "suggestion" | "approval_note" | "system_note";
  content: string;
  is_resolved: boolean;
  created_at?: string | null;
  answers?: GRComment[];
}

export interface InProgressForumGR {
  id: number;
  filename: string;
  department?: string | null;
  gr_number_canonical?: string | null;
  date?: string | null;
  status: string;
  shared_with_dept: boolean;
  shared_at?: string | null;
  shared_by_user?: string | null;
  is_finalized?: boolean | null;
  version_count: number;
  comment_count: number;
  unresolved_comment_count: number;
  is_fully_approved?: boolean;
}

export async function fetchInProgressForumGRs(): Promise<InProgressForumGR[]> {
  const res = await fetch(`${API_BASE_URL}/forum/in-progress`);
  if (!res.ok) throw new ApiError(res.status, "Failed to fetch in-progress GRs");
  return res.json();
}

export async function fetchSharedGRDetail(grId: number): Promise<{
  gr_document: any;
  comments: GRComment[];
  versions: any[];
}> {
  const res = await fetch(`${API_BASE_URL}/forum/${grId}`);
  if (!res.ok) throw new ApiError(res.status, "Failed to fetch shared GR detail");
  return res.json();
}

export async function postGRComment(
  grId: number,
  payload: {
    user_name: string;
    user_role: string;
    user_department?: string;
    comment_type: string;
    content: string;
    parent_id?: number | null;
  }
): Promise<GRComment> {
  const res = await fetch(`${API_BASE_URL}/forum/${grId}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, "Failed to post comment");
  return res.json();
}


export async function toggleCommentResolution(
  commentId: number,
  isResolved: boolean
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/forum/comments/${commentId}/resolve`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ is_resolved: isResolved }),
  });
  if (!res.ok) throw new ApiError(res.status, "Failed to update resolution status");
}

export async function shareDraftWithDepartment(
  draftId: number,
  userName: string = "Drafting Officer"
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/drafts/${draftId}/share?user_name=${encodeURIComponent(userName)}`, {
    method: "POST",
  });
  if (!res.ok) throw new ApiError(res.status, "Failed to share draft with department");
}

export interface FinalizeResult {
  exportType: "pdf" | "txt";
  /** For txt: the text content to download */
  textContent?: string;
  /** For pdf: the blob to download */
  pdfBlob?: Blob;
  filename: string;
}

export async function finalizeDraftAndExport(draftId: number): Promise<FinalizeResult> {
  const res = await fetch(`${API_BASE_URL}/drafts/${draftId}/pdf`);
  if (!res.ok) throw new ApiError(res.status, "Failed to export PDF");

  const pdfBlob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : `GR_${draftId}.pdf`;
  return { exportType: "pdf", pdfBlob, filename };
}


export async function banishDraftFromForum(draftId: number): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/drafts/${draftId}/banish`, {
    method: "POST",
  });
  if (!res.ok) throw new ApiError(res.status, "Failed to banish draft from forum");
}

// ── PDF Template API ──────────────────────────────────────────────────────────


export interface PdfTemplate {
  id: number;
  department: string;
  header_line: string;
  footer_text: string;
  font_family: string;
  margins_pt: number;
  logo_base64?: string;
  updated_at: string;
}

export async function getTemplate(): Promise<PdfTemplate> {
  const res = await fetch(`${API_BASE_URL}/template`);
  if (!res.ok) throw new ApiError(res.status, "Failed to fetch template");
  return res.json();
}

export async function updateTemplate(fields: Partial<Omit<PdfTemplate, "id" | "updated_at">>): Promise<PdfTemplate> {
  const res = await fetch(`${API_BASE_URL}/template`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new ApiError(res.status, "Failed to update template");
  return res.json();
}

export function getTemplatePdfPreviewUrl(): string {
  return `${API_BASE_URL}/template/preview`;
}
