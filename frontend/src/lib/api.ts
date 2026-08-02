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
  relevance_note?: string | null;
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

/**
 * Run conflict + glossary terminology checks in parallel (partial per-section success).
 */
export async function analyzeDraft(
  draftText: string,
  opts?: { topK?: number; hops?: number }
): Promise<DraftAnalysisResponse> {
  const payload = {
    draft_text: draftText,
    top_k: opts?.topK ?? 15,
    hops: opts?.hops ?? 1,
  };

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
