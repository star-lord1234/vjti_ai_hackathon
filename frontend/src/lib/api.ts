/**
 * Typed API client for FastAPI backend endpoints.
 */

export interface AffectedGR {
  label: string;
  gr_number_canonical: string;
  relevance_note: string;
}

export interface ConflictFinding {
  conflicting: boolean;
  explanation: string;
  conflicting_clauses: string[];
  affected_grs: AffectedGR[];
  confidence: number;
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
 * Health check endpoint ping
 */
export async function checkHealth(): Promise<{ status: string; db: boolean }> {
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
