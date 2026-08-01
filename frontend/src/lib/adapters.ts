import { ConflictFinding } from "./api";

export type Severity = "high" | "medium" | "low";

export interface Finding {
  id: string;
  severity: Severity;
  clauseNumber: string;
  summary: string;
  analysis: string;
  recommendation: string;
  page: number;
  lineRange: [number, number];
  category: string;
}

/**
 * Derive finding severity badge level based on confidence score (0-1).
 * - > 0.75: "high"
 * - > 0.4: "medium"
 * - else: "low"
 */
export function deriveSeverity(confidence: number): Severity {
  if (confidence > 0.75) return "high";
  if (confidence > 0.4) return "medium";
  return "low";
}

/**
 * Adapter function mapping backend ConflictFinding response object into a Finding[] array
 * for display in the review screen.
 */
export function mapConflictFindingToFindings(
  conflictResult: ConflictFinding
): Finding[] {
  if (!conflictResult.conflicting) {
    return [];
  }

  const severity = deriveSeverity(conflictResult.confidence);
  const clauses = conflictResult.conflicting_clauses || [];
  const grs = conflictResult.affected_grs || [];

  // If conflicting clauses are returned, map one Finding per conflicting clause
  if (clauses.length > 0) {
    return clauses.map((clauseText, idx) => {
      const matchedGr = grs[idx] || grs[0];
      const clauseLabel = matchedGr?.label || `Clause #${idx + 1}`;
      const category = matchedGr?.label || matchedGr?.gr_number_canonical || "Jurisdiction";

      return {
        id: `f-${idx + 1}`,
        severity,
        clauseNumber: clauseLabel,
        summary: clauseText,
        analysis: `${conflictResult.explanation}${
          matchedGr?.relevance_note ? ` Relevant reference: ${matchedGr.relevance_note}` : ""
        }`,
        recommendation:
          "Review recommended: Verify draft clause alignment against cited Government Resolution provisions.",
        // Known limitation: page numbers and line ranges are defaulted since raw text extraction is used
        page: 1,
        lineRange: [0, 0] as [number, number],
        category,
      };
    });
  }

  // Fallback: If affected_grs exists but no individual clauses were listed
  if (grs.length > 0) {
    return grs.map((gr, idx) => ({
      id: `f-${idx + 1}`,
      severity,
      clauseNumber: gr.label || `GR ${idx + 1}`,
      summary: gr.relevance_note || `Potential conflict with ${gr.gr_number_canonical || gr.label}`,
      analysis: conflictResult.explanation,
      recommendation:
        "Review recommended: Align draft language with existing statutory guidelines.",
      page: 1,
      lineRange: [0, 0] as [number, number],
      category: gr.label || "Legal Conflict",
    }));
  }

  // If marked conflicting but both lists are empty, return 1 general finding
  return [
    {
      id: "f-1",
      severity,
      clauseNumber: "Draft Text",
      summary: "Potential policy conflict detected in draft text.",
      analysis: conflictResult.explanation || "The backend detected a potential policy contradiction.",
      recommendation: "Review recommended: Conduct manual legal verification.",
      page: 1,
      lineRange: [0, 0] as [number, number],
      category: "Policy",
    },
  ];
}
