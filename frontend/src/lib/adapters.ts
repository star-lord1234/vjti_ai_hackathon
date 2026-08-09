import {
  AffectedGR,
  ConflictFinding,
  ConflictPair,
  TemplateCheckSection,
} from "./api";

export type Severity = "high" | "medium" | "low";

export interface Finding {
  id: string;
  severity: Severity;
  clauseNumber: string;
  summary: string;
  matched_text?: string;
  matchedText?: string;
  draftExcerpt?: string;
  corpusExcerpt?: string;
  corpusGrLabel?: string;
  corpusGrNumber?: string;
  analysis: string;
  recommendation: string;
  page: number;
  lineRange: [number, number];
  category: string;
  conflictType?: string;
  location?: string;
  crossDepartmental?: boolean;
}

/**
 * Derive finding severity badge level based on confidence score (0-1).
 */
export function deriveSeverity(confidence: number): Severity {
  if (confidence > 0.75) return "high";
  if (confidence > 0.4) return "medium";
  return "low";
}

function tokenize(text: string): Set<string> {
  return new Set(
    text
      .toLowerCase()
      .replace(/[^\w\u0900-\u097F\s]/g, " ")
      .split(/\s+/)
      .filter((t) => t.length > 3),
  );
}

function tokenOverlapScore(a: string, b: string): number {
  const tokensA = tokenize(a);
  const tokensB = tokenize(b);
  if (tokensA.size === 0 || tokensB.size === 0) return 0;
  let overlap = 0;
  for (const t of tokensA) {
    if (tokensB.has(t)) overlap += 1;
  }
  return overlap / Math.max(tokensA.size, tokensB.size);
}

/**
 * Match a conflicting clause to the best affected GR by text overlap,
 * not naive array index pairing.
 */
export function findBestGrForClause(
  clause: string,
  grs: AffectedGR[],
  usedLabels: Set<string>,
): AffectedGR | undefined {
  if (grs.length === 0) return undefined;

  let best: AffectedGR | undefined;
  let bestScore = -1;

  for (const gr of grs) {
    if (usedLabels.has(gr.label)) continue;

    const note = gr.relevance_note || "";
    const corpus = gr.corpus_excerpt || "";
    const canon = gr.gr_number_canonical || "";
    const haystack = `${note} ${corpus} ${canon} ${gr.label}`;

    let score = tokenOverlapScore(clause, haystack);
    if (note && clause.length > 20) {
      score = Math.max(score, tokenOverlapScore(clause, note) * 1.2);
    }

    if (score > bestScore) {
      bestScore = score;
      best = gr;
    }
  }

  if (best) return best;

  for (const gr of grs) {
    const note = gr.relevance_note || "";
    const corpus = gr.corpus_excerpt || "";
    const score = tokenOverlapScore(
      clause,
      `${note} ${corpus} ${gr.gr_number_canonical || ""}`,
    );
    if (score > bestScore) {
      bestScore = score;
      best = gr;
    }
  }

  return best ?? grs[0];
}

/**
 * Per-clause severity: decay slightly by rank, bump if cross-departmental.
 */
export function deriveClauseSeverity(
  globalConfidence: number,
  clauseIndex: number,
  totalClauses: number,
  crossDepartmental: boolean,
): Severity {
  const rankDecay = totalClauses > 1 ? clauseIndex * 0.06 : 0;
  let effective = globalConfidence - rankDecay;
  if (crossDepartmental) effective = Math.max(effective, 0.55);
  return deriveSeverity(effective);
}

function findingFromPair(
  pair: ConflictPair,
  idx: number,
  conflictResult: ConflictFinding,
  severity: Severity,
  crossDept: boolean,
): Finding {
  const grLabel = pair.gr_label?.replace(/^\[|\]$/g, "") || `GR ${idx + 1}`;

  // Prefer normalized (human-readable), then original, then canonical as last resort
  const displayGrNumber =
    pair.gr_number_normalized ||
    pair.gr_number_original ||
    pair.gr_number_canonical ||
    undefined;

  // Per-pair analysis: use per_conflict_explanation if available, else relevance_note only
  // Never paste the global explanation into every card
  const perPairAnalysis =
    pair.per_conflict_explanation ||
    pair.relevance_note ||
    (conflictResult.supersession_detected ? "[Supersession detected]" : null) ||
    "Insufficient evidence — no per-conflict analysis available.";

  // Per-pair recommendation: use backend-provided one if available
  const perPairRecommendation =
    pair.recommendation ||
    `Insufficient evidence — review ${grLabel} for conflicting provisions before drafting.`;

  const draftClauseText = pair.draft_clause || pair.relevance_note || "Conflict detected";
  return {
    id: `f-${idx + 1}`,
    severity,
    clauseNumber: grLabel,
    summary: draftClauseText,
    matched_text: draftClauseText,
    matchedText: draftClauseText,
    draftExcerpt: pair.draft_proposes || draftClauseText,
    corpusExcerpt: pair.existing_gr_provides || pair.corpus_excerpt || "",
    corpusGrLabel: pair.gr_label || "",
    corpusGrNumber: displayGrNumber,
    analysis: perPairAnalysis,
    recommendation: perPairRecommendation,
    page: 1,
    lineRange: [0, 0],
    category: pair.conflict_type
      ? `${pair.conflict_type.charAt(0).toUpperCase()}${pair.conflict_type.slice(1)}`
      : displayGrNumber || grLabel,
    conflictType: pair.conflict_type || undefined,
    crossDepartmental: crossDept,
  };
}

/**
 * Map backend ConflictFinding into UI Finding[] with draft vs corpus excerpts.
 */
export function mapConflictFindingToFindings(
  conflictResult: ConflictFinding,
): Finding[] {
  if (!conflictResult.conflicting) {
    return [];
  }

  const globalConfidence = conflictResult.confidence ?? 0.7;
  const crossDept = Boolean(conflictResult.cross_departmental);
  const pairs = conflictResult.conflict_pairs || [];
  const clauses = conflictResult.conflicting_clauses || [];
  const grs = conflictResult.affected_grs || [];

  if (pairs.length > 0) {
    // Deduplicate pairs that share the same (draft_clause, gr_label) key
    const seen = new Set<string>();
    const dedupedPairs = pairs.filter((pair) => {
      const clauseStr = pair.draft_clause || pair.relevance_note || "";
      const labelStr = pair.gr_label || "";
      const key = `${clauseStr.slice(0, 120)}::${labelStr}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    return dedupedPairs.map((pair, idx) =>
      findingFromPair(
        pair,
        idx,
        conflictResult,
        deriveClauseSeverity(
          globalConfidence,
          idx,
          dedupedPairs.length,
          crossDept,
        ),
        crossDept,
      ),
    );
  }

  const usedLabels = new Set<string>();

  if (clauses.length > 0) {
    return clauses.map((clauseText, idx) => {
      const matchedGr = findBestGrForClause(clauseText, grs, usedLabels);
      if (matchedGr?.label) usedLabels.add(matchedGr.label);

      const clauseLabel =
        matchedGr?.label?.replace(/^\[|\]$/g, "") || `Clause ${idx + 1}`;

      // Prefer normalized (human-readable), then original, then canonical
      const displayGrNumber =
        (matchedGr as any)?.gr_number_normalized ||
        (matchedGr as any)?.gr_number_original ||
        matchedGr?.gr_number_canonical ||
        undefined;

      const category = displayGrNumber || matchedGr?.label || "Policy Conflict";
      const corpusExcerpt =
        matchedGr?.corpus_excerpt || matchedGr?.relevance_note || "";

      // Per-clause analysis: use relevance_note, never the global explanation
      const perClauseAnalysis = matchedGr?.relevance_note
        ? `${matchedGr.relevance_note}${
            conflictResult.supersession_detected
              ? " [Supersession detected]"
              : ""
          }`
        : conflictResult.supersession_detected
          ? "[Supersession detected]"
          : "Insufficient evidence — no per-clause analysis available.";

      const perClauseRecommendation = matchedGr?.relevance_note
        ? `Review ${clauseLabel}: ${matchedGr.relevance_note}. Align draft clause or state the basis for deviation.`
        : `Insufficient evidence — review ${clauseLabel} for conflicting provisions before drafting.`;

      return {
        id: `f-${idx + 1}`,
        severity: deriveClauseSeverity(
          globalConfidence,
          idx,
          clauses.length,
          crossDept,
        ),
        clauseNumber: clauseLabel,
        summary: clauseText,
        matched_text: clauseText,
        matchedText: clauseText,
        draftExcerpt: clauseText,
        corpusExcerpt,
        corpusGrLabel: matchedGr?.label,
        corpusGrNumber: displayGrNumber,
        analysis: perClauseAnalysis,
        recommendation: perClauseRecommendation,
        page: 1,
        lineRange: [0, 0] as [number, number],
        category,
        conflictType: undefined,
        crossDepartmental: crossDept,
      };
    });
  }

  if (grs.length > 0) {
    return grs.map((gr, idx) => {
      // Prefer normalized (human-readable), then original, then canonical
      const displayGrNumber =
        (gr as any).gr_number_normalized ||
        (gr as any).gr_number_original ||
        gr.gr_number_canonical ||
        undefined;

      const perGrAnalysis =
        gr.relevance_note ||
        "Insufficient evidence — no per-GR analysis available.";

      const perGrRecommendation = gr.relevance_note
        ? `Review ${gr.label}: ${gr.relevance_note}. Align draft language or state the basis for deviation.`
        : `Insufficient evidence — review ${gr.label} for conflicting provisions before drafting.`;

      return {
        id: `f-${idx + 1}`,
        severity: deriveClauseSeverity(
          globalConfidence,
          idx,
          grs.length,
          crossDept,
        ),
        clauseNumber: gr.label || `GR ${idx + 1}`,
        summary:
          gr.relevance_note ||
          `Potential conflict with ${displayGrNumber || gr.label}`,
        matched_text: gr.relevance_note || "",
        matchedText: gr.relevance_note || "",
        draftExcerpt: "",
        corpusExcerpt: gr.corpus_excerpt || gr.relevance_note || "",
        corpusGrLabel: gr.label,
        corpusGrNumber: displayGrNumber,
        analysis: perGrAnalysis,
        recommendation: perGrRecommendation,
        page: 1,
        lineRange: [0, 0] as [number, number],
        category: gr.label || "Legal Conflict",
        conflictType: undefined,
        crossDepartmental: crossDept,
      };
    });
  }

  return [];
}

/**
 * Map backend template findings into UI Finding[] for the shared findings panel.
 */
export function mapTemplateFindingsToFindings(
  templateCheck: TemplateCheckSection | null | undefined,
): Finding[] {
  if (!templateCheck?.findings?.length) return [];

  return templateCheck.findings.map((f) => ({
    id: f.id,
    severity: f.severity,
    clauseNumber: f.summary,
    summary: f.description || f.summary,
    matched_text: f.matched_text || "",
    matchedText: f.matched_text || "",
    draftExcerpt: f.matched_text || "",
    analysis: f.analysis || f.description || "",
    recommendation:
      f.recommendation ||
      "Adjust draft structure to follow standard Maharashtra GR section order.",
    page: 1,
    lineRange: (f.line_range as [number, number]) || [
      f.line_number || 0,
      f.line_number || 0,
    ],
    category: "Template Structure",
    location: f.location,
  }));
}
