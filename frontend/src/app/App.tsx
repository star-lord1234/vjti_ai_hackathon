import { useState, useEffect, useRef, useCallback } from "react";
import {
  Search,
  Bell,
  ChevronDown,
  Upload,
  FileText,
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
  X,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  Loader2,
  Eye,
  Shield,
  BookOpen,
  BarChart3,
  Download,
  MoreHorizontal,
  Flag,
  Bookmark,
  RefreshCw,
  ArrowRight,
  MapPin,
  Layers,
  Clock,
  TrendingUp,
  FileCode,
} from "lucide-react";
import { checkHealth, checkConflict, ConflictFinding, ApiError } from "../lib/api";
import { mapConflictFindingToFindings, Finding, Severity } from "../lib/adapters";

// ─── Types ────────────────────────────────────────────────────────────────────

type Phase = "upload" | "processing" | "review";

// ─── Default Sample Data (Fallback) ───────────────────────────────────────────

const SAMPLE_DRAFT_TEXT = `GOVERNMENT OF INDIA
MINISTRY OF ENVIRONMENT, FOREST AND CLIMATE CHANGE

RESOLUTION

Subject: National Green Infrastructure Development and Environmental Clearance Streamlining Resolution, 2024 — Guidelines for Implementation

Section 4.2(b)
State Authorities shall exercise EXCLUSIVE JURISDICTION over environmental impact assessments, including the power to commission, review, approve, or reject EIA reports, independent of any Central Government authority or agency, in respect of all projects not explicitly listed in Schedule I.

Section 7.1
The Competent Authority is hereby delegated the power to approve procurement of goods, services, and works up to a value of Rupees Eighty-Five Crore (₹85,00,00,000) without prior Parliamentary sanction, for projects falling under this Resolution.`;

const PROCESSING_STEPS = [
  { id: "read", label: "Reading Document", sub: "Parsing document structure and metadata", icon: BookOpen },
  { id: "extract", label: "Extracting Clauses", sub: "Identifying draft resolution provisions", icon: FileText },
  { id: "detect", label: "Detecting Conflicts", sub: "Cross-referencing statutory database & Neo4j graph", icon: Shield },
  { id: "analyse", label: "Generating Analysis", sub: "Producing severity assessments", icon: BarChart3 },
  { id: "complete", label: "Review Complete", sub: "Findings ready for review", icon: CheckCircle2 },
];

interface DocPara {
  id: string;
  type: "header" | "subject" | "section" | "filler";
  label?: string;
  text: string;
  highlight?: string;
  highlightPhrase?: string;
}

const DEFAULT_PARAGRAPHS: DocPara[] = [
  {
    id: "header",
    type: "header",
    text: "GOVERNMENT OF INDIA\nMINISTRY OF ENVIRONMENT, FOREST AND CLIMATE CHANGE\n\nRESOLUTION\n\nNo. 14025/7/2024-ENV\nNew Delhi, dated the 18th July, 2024",
  },
  {
    id: "subject",
    type: "subject",
    text: "Subject: National Green Infrastructure Development and Environmental Clearance Streamlining Resolution, 2024 — Guidelines for Implementation and Operational Framework",
  },
  {
    id: "s4",
    type: "section",
    label: "Section 4 — Jurisdiction and Authority",
    highlight: "f-1",
    highlightPhrase:
      "EXCLUSIVE JURISDICTION over environmental impact assessments",
    text: "4.1 The Ministry shall be the nodal Ministry for all matters arising under this Resolution.\n\n4.2 State Authorities shall exercise (b) EXCLUSIVE JURISDICTION over environmental impact assessments, including the power to commission, review, approve, or reject EIA reports, independent of any Central Government authority or agency.",
  },
  {
    id: "s7",
    type: "section",
    label: "Section 7 — Financial Powers and Procurement",
    highlight: "f-2",
    highlightPhrase:
      "Rupees Eighty-Five Crore (₹85,00,00,000) without prior Parliamentary sanction",
    text: "7.1 The Competent Authority is hereby delegated the power to approve procurement of goods, services, and works up to a value of Rupees Eighty-Five Crore (₹85,00,00,000) without prior Parliamentary sanction, for projects falling under this Resolution.",
  },
];

// ─── Severity helpers ─────────────────────────────────────────────────────────

function severityConfig(s: Severity) {
  switch (s) {
    case "high":
      return {
        color: "text-red-600",
        bg: "bg-red-50",
        border: "border-red-200",
        dot: "bg-red-500",
        badge: "bg-red-100 text-red-700",
        barBg: "bg-red-500",
        icon: AlertCircle,
        label: "High",
      };
    case "medium":
      return {
        color: "text-amber-600",
        bg: "bg-amber-50",
        border: "border-amber-200",
        dot: "bg-amber-500",
        badge: "bg-amber-100 text-amber-700",
        barBg: "bg-amber-500",
        icon: AlertTriangle,
        label: "Medium",
      };
    case "low":
      return {
        color: "text-blue-600",
        bg: "bg-blue-50",
        border: "border-blue-200",
        dot: "bg-blue-500",
        badge: "bg-blue-100 text-blue-700",
        barBg: "bg-blue-500",
        icon: Info,
        label: "Low",
      };
  }
}

// ─── SeverityBadge ────────────────────────────────────────────────────────────

function SeverityBadge({ severity, size = "sm" }: { severity: Severity; size?: "sm" | "md" }) {
  const cfg = severityConfig(severity);
  const Icon = cfg.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md font-semibold ${cfg.badge} ${
        size === "md" ? "px-2.5 py-1 text-xs" : "px-2 py-0.5 text-xs"
      }`}
    >
      <Icon size={size === "md" ? 12 : 11} strokeWidth={2.5} />
      {cfg.label}
    </span>
  );
}

// ─── Toast ────────────────────────────────────────────────────────────────────

function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 2600);
    return () => clearTimeout(t);
  }, [onDone]);
  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] bg-[#111827] text-white text-sm font-medium px-5 py-3 rounded-xl shadow-xl flex items-center gap-2.5 animate-fade-in">
      <CheckCircle2 size={15} className="text-[#22C55E]" />
      {message}
    </div>
  );
}

// ─── FindingCard ──────────────────────────────────────────────────────────────

function FindingCard({
  finding,
  active,
  bookmarked,
  onClick,
  onBookmark,
}: {
  finding: Finding;
  active: boolean;
  bookmarked: boolean;
  onClick: () => void;
  onBookmark: (e: React.MouseEvent) => void;
}) {
  const cfg = severityConfig(finding.severity);
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-2xl border transition-all duration-200 group focus:outline-none focus-visible:ring-2 focus-visible:ring-[#2563EB]/40 ${
        active
          ? `${cfg.border} ${cfg.bg} shadow-md`
          : "border-[#E5E7EB] bg-white hover:shadow-md hover:-translate-y-0.5 hover:border-[#D1D5DB]"
      }`}
      style={{ fontFamily: "Inter, sans-serif" }}
    >
      <div
        className={`h-0.5 rounded-t-2xl w-full ${cfg.barBg} ${active ? "opacity-100" : "opacity-0 group-hover:opacity-60"} transition-opacity`}
      />
      <div className="p-4">
        <div className="flex items-start justify-between gap-2 mb-2.5">
          <SeverityBadge severity={finding.severity} />
          <div className="flex items-center gap-1.5">
            <span className="text-xs text-[#9CA3AF] font-mono bg-[#F9FAFB] px-2 py-0.5 rounded-md border border-[#E5E7EB]">
              {finding.clauseNumber}
            </span>
            <button
              onClick={onBookmark}
              className={`p-1 rounded-lg transition-colors ${
                bookmarked
                  ? "text-[#2563EB]"
                  : "text-[#D1D5DB] hover:text-[#9CA3AF]"
              }`}
            >
              <Bookmark size={13} fill={bookmarked ? "currentColor" : "none"} />
            </button>
          </div>
        </div>

        <p className="text-sm font-medium text-[#111827] leading-snug mb-3">
          {finding.summary}
        </p>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#9CA3AF] bg-[#F9FAFB] px-2 py-1 rounded-lg border border-[#E5E7EB]">
              {finding.category}
            </span>
            <span className="flex items-center gap-1 text-xs text-[#9CA3AF]">
              <MapPin size={10} />
              Pg {finding.page}
            </span>
          </div>
          <span
            className={`text-xs font-semibold flex items-center gap-1 transition-all duration-150 ${
              active ? cfg.color : "text-[#2563EB]"
            } group-hover:gap-1.5`}
          >
            <Eye size={12} />
            {active ? "Viewing" : "View Analysis"}
          </span>
        </div>
      </div>
    </button>
  );
}

// ─── InspectorDrawer ──────────────────────────────────────────────────────────

function InspectorDrawer({
  finding,
  bookmarked,
  onClose,
  onBookmark,
  onJump,
  onFlag,
}: {
  finding: Finding | null;
  bookmarked: boolean;
  onClose: () => void;
  onBookmark: () => void;
  onJump: () => void;
  onFlag: () => void;
}) {
  const cfg = finding ? severityConfig(finding.severity) : null;
  const Icon = cfg?.icon ?? Info;

  return (
    <>
      <div
        className={`fixed inset-0 z-40 transition-opacity duration-300 ${
          finding ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
        }`}
        onClick={onClose}
      />
      <div
        className={`fixed top-0 right-0 h-full w-[460px] z-50 bg-white border-l border-[#E5E7EB] shadow-2xl flex flex-col transition-transform duration-300 ease-in-out ${
          finding ? "translate-x-0" : "translate-x-full"
        }`}
        style={{ fontFamily: "Inter, sans-serif" }}
      >
        {finding && cfg && (
          <>
            <div className={`h-1 w-full ${cfg.barBg}`} />

            <div className="flex items-start justify-between px-6 py-5 border-b border-[#E5E7EB]">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2">
                  <SeverityBadge severity={finding.severity} size="md" />
                  <span className="text-xs text-[#9CA3AF] font-mono bg-[#F9FAFB] px-2 py-0.5 rounded-md border border-[#E5E7EB]">
                    {finding.clauseNumber}
                  </span>
                </div>
                <h2 className="text-sm font-semibold text-[#111827] leading-snug pr-2">
                  {finding.summary}
                </h2>
              </div>
              <button
                onClick={onClose}
                className="ml-3 p-2 rounded-xl hover:bg-[#F3F4F6] transition-colors text-[#9CA3AF] hover:text-[#374151] flex-shrink-0"
              >
                <X size={17} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
              <div className="grid grid-cols-3 gap-2.5">
                {[
                  { label: "Category", value: finding.category, icon: Layers },
                  { label: "Page", value: `Page ${finding.page}`, icon: FileText },
                  {
                    label: "Lines",
                    value: `${finding.lineRange[0]}–${finding.lineRange[1]}`,
                    icon: MapPin,
                  },
                ].map(({ label, value, icon: MetaIcon }) => (
                  <div
                    key={label}
                    className="bg-[#F9FAFB] rounded-xl p-3 border border-[#E5E7EB]"
                  >
                    <div className="flex items-center gap-1 mb-1">
                      <MetaIcon size={11} className="text-[#9CA3AF]" />
                      <p className="text-xs text-[#9CA3AF]">{label}</p>
                    </div>
                    <p className="text-xs font-semibold text-[#111827]">{value}</p>
                  </div>
                ))}
              </div>

              <button
                onClick={onJump}
                className="w-full flex items-center justify-between px-4 py-3 rounded-xl border border-[#E5E7EB] hover:border-[#2563EB] hover:bg-[#EFF6FF] group transition-all duration-150"
              >
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-lg bg-[#EFF6FF] group-hover:bg-white flex items-center justify-center transition-colors">
                    <Eye size={12} className="text-[#2563EB]" />
                  </div>
                  <span className="text-sm font-medium text-[#374151] group-hover:text-[#2563EB] transition-colors">
                    Jump to clause in document
                  </span>
                </div>
                <ArrowRight size={14} className="text-[#9CA3AF] group-hover:text-[#2563EB] transition-colors" />
              </button>

              <div>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-5 h-5 rounded-md bg-[#EFF6FF] flex items-center justify-center">
                    <BarChart3 size={11} className="text-[#2563EB]" />
                  </div>
                  <h3 className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">
                    Detailed AI Analysis
                  </h3>
                </div>
                <div className={`rounded-2xl p-4 border ${cfg.border} ${cfg.bg}`}>
                  <div className="flex items-start gap-2 mb-2">
                    <Icon size={14} className={`${cfg.color} mt-0.5 flex-shrink-0`} />
                    <p className="text-sm text-[#374151] leading-relaxed">
                      {finding.analysis}
                    </p>
                  </div>
                </div>
              </div>

              <div>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-5 h-5 rounded-md bg-[#F0FDF4] flex items-center justify-center">
                    <CheckCircle2 size={11} className="text-[#22C55E]" />
                  </div>
                  <h3 className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">
                    Recommendation
                  </h3>
                </div>
                <div className="rounded-2xl p-4 border border-[#BBF7D0] bg-[#F0FDF4]">
                  <p className="text-sm text-[#15803D] leading-relaxed">
                    {finding.recommendation}
                  </p>
                </div>
              </div>
            </div>

            <div className="px-5 py-4 border-t border-[#E5E7EB] flex items-center gap-2.5">
              <button
                onClick={onFlag}
                className="flex-1 py-2.5 rounded-xl bg-[#2563EB] text-white text-sm font-semibold hover:bg-[#1D4ED8] active:bg-[#1E40AF] transition-colors flex items-center justify-center gap-2"
              >
                <Flag size={13} />
                Flag for Review
              </button>
              <button
                onClick={onBookmark}
                className={`flex-1 py-2.5 rounded-xl border text-sm font-semibold transition-colors flex items-center justify-center gap-2 ${
                  bookmarked
                    ? "border-[#2563EB] text-[#2563EB] bg-[#EFF6FF]"
                    : "border-[#E5E7EB] text-[#374151] hover:bg-[#F9FAFB]"
                }`}
              >
                <Bookmark size={13} fill={bookmarked ? "currentColor" : "none"} />
                {bookmarked ? "Saved" : "Save Finding"}
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}

// ─── Highlight matching helpers ───────────────────────────────────────────────

/** Normalize for matching only — never mutate displayed text. */
function normalizeForMatch(text: string): string {
  return text
    .replace(/[\u2018\u2019\u201A\u201B]/g, "'")
    .replace(/[\u201C\u201D\u201E\u201F]/g, '"')
    .replace(/\s+/g, " ")
    .trim();
}

function normalizeChar(ch: string): string {
  if (/[\u2018\u2019\u201A\u201B]/.test(ch)) return "'";
  if (/[\u201C\u201D\u201E\u201F]/.test(ch)) return '"';
  if (/\s/.test(ch)) return " ";
  return ch;
}

/**
 * Build normalized haystack + index map so a normalized match can be
 * sliced back onto the original (display) string.
 */
function buildNormalizedIndex(original: string): {
  normalized: string;
  normToOrig: number[];
} {
  const chars: string[] = [];
  const normToOrig: number[] = [];
  let lastWasSpace = true; // trim leading whitespace
  for (let i = 0; i < original.length; i++) {
    const nc = normalizeChar(original[i]);
    if (nc === " ") {
      if (lastWasSpace) continue;
      lastWasSpace = true;
      chars.push(" ");
      normToOrig.push(i);
    } else {
      lastWasSpace = false;
      chars.push(nc);
      normToOrig.push(i);
    }
  }
  while (chars.length > 0 && chars[chars.length - 1] === " ") {
    chars.pop();
    normToOrig.pop();
  }
  return { normalized: chars.join(""), normToOrig };
}

function findExactRange(
  original: string,
  snippet: string
): { start: number; end: number } | null {
  const needle = normalizeForMatch(snippet);
  if (!needle) return null;
  const { normalized, normToOrig } = buildNormalizedIndex(original);
  const idx = normalized.indexOf(needle);
  if (idx === -1) return null;
  const start = normToOrig[idx];
  const last = normToOrig[idx + needle.length - 1];
  return { start, end: last + 1 };
}

function tokenOverlapRatio(a: string, b: string): number {
  const tokensA = new Set(
    normalizeForMatch(a)
      .toLowerCase()
      .split(" ")
      .filter(Boolean)
  );
  const tokensB = new Set(
    normalizeForMatch(b)
      .toLowerCase()
      .split(" ")
      .filter(Boolean)
  );
  if (tokensA.size === 0 || tokensB.size === 0) return 0;
  let overlap = 0;
  for (const t of tokensA) {
    if (tokensB.has(t)) overlap += 1;
  }
  return overlap / Math.max(tokensA.size, tokensB.size);
}

type HighlightMatch =
  | { kind: "exact"; paragraphIndex: number; start: number; end: number }
  | { kind: "fuzzy"; paragraphIndex: number };

function findHighlightMatch(paragraphs: string[], snippet: string): HighlightMatch | null {
  const normSnippet = normalizeForMatch(snippet);
  if (!normSnippet) return null;

  for (let i = 0; i < paragraphs.length; i++) {
    const range = findExactRange(paragraphs[i], snippet);
    if (range) {
      return { kind: "exact", paragraphIndex: i, start: range.start, end: range.end };
    }
  }

  let bestIdx = -1;
  let bestScore = 0;
  for (let i = 0; i < paragraphs.length; i++) {
    const score = tokenOverlapRatio(paragraphs[i], snippet);
    if (score > bestScore) {
      bestScore = score;
      bestIdx = i;
    }
  }
  if (bestIdx >= 0 && bestScore >= 0.2) {
    return { kind: "fuzzy", paragraphIndex: bestIdx };
  }
  return null;
}

function highlightMarkClass(severity: Severity): string {
  switch (severity) {
    case "high":
      return "bg-red-200/80 text-red-950 rounded-sm px-0.5 box-decoration-clone";
    case "medium":
      return "bg-amber-200/80 text-amber-950 rounded-sm px-0.5 box-decoration-clone";
    case "low":
      return "bg-blue-200/80 text-blue-950 rounded-sm px-0.5 box-decoration-clone";
  }
}

function highlightBlockClass(severity: Severity): string {
  switch (severity) {
    case "high":
      return "bg-red-50 outline outline-2 outline-red-300 rounded-sm";
    case "medium":
      return "bg-amber-50 outline outline-2 outline-amber-300 rounded-sm";
    case "low":
      return "bg-blue-50 outline outline-2 outline-blue-300 rounded-sm";
  }
}

/** Subset of Finding fields needed for document highlighting (generic across finding types). */
type HighlightableFinding = {
  id: string;
  /** Text snippet to locate in the draft — sourced from Finding.summary today. */
  matchedText: string;
  severity: Severity;
};

function renderHighlightedText(
  text: string,
  match: HighlightMatch | null,
  paragraphIndex: number,
  severity: Severity
) {
  if (!match || match.paragraphIndex !== paragraphIndex) {
    return text;
  }
  if (match.kind === "fuzzy") {
    return <mark className={highlightMarkClass(severity)}>{text}</mark>;
  }
  const before = text.slice(0, match.start);
  const mid = text.slice(match.start, match.end);
  const after = text.slice(match.end);
  return (
    <>
      {before}
      <mark className={highlightMarkClass(severity)}>{mid}</mark>
      {after}
    </>
  );
}

// ─── DocumentViewer ───────────────────────────────────────────────────────────

function DocumentViewer({
  draftText,
  highlightedFinding,
  zoom,
  scrollKey = 0,
}: {
  draftText: string;
  highlightedFinding: HighlightableFinding | null;
  zoom: number;
  /** Bump to re-scroll to the current highlight (e.g. Jump to clause). */
  scrollKey?: number;
}) {
  const highlightRef = useRef<HTMLDivElement>(null);

  const paragraphs = draftText
    ? draftText.split(/\n\n+/).filter((b) => b.trim().length > 0)
    : [];

  const defaultTexts = DEFAULT_PARAGRAPHS.map((p) =>
    p.label ? `${p.label}\n${p.text}` : p.text
  );
  const textsForMatch = paragraphs.length > 0 ? paragraphs : defaultTexts;

  const match =
    highlightedFinding?.matchedText
      ? findHighlightMatch(textsForMatch, highlightedFinding.matchedText)
      : null;

  // Scroll matched paragraph into view when the selected finding (or jump request) changes
  useEffect(() => {
    if (!highlightedFinding?.id) return;
    const t = window.setTimeout(() => {
      highlightRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 50);
    return () => window.clearTimeout(t);
  }, [highlightedFinding?.id, scrollKey]);

  return (
    <div
      className="flex-1 overflow-y-auto bg-[#525659] flex justify-center py-8 px-6"
      style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
    >
      <div
        className="bg-white shadow-2xl w-full max-w-3xl origin-top transition-all duration-200"
        style={{
          zoom: `${zoom}%`,
          minHeight: "1056px",
          padding: "88px 80px",
          fontSize: "13.5px",
          lineHeight: "1.85",
          color: "#1a1a1a",
        }}
      >
        {paragraphs.length > 0 ? (
          paragraphs.map((p, idx) => {
            const isHighlighted = Boolean(highlightedFinding && match?.paragraphIndex === idx);
            return (
              <div
                key={idx}
                ref={isHighlighted ? highlightRef : undefined}
                className={`mb-6 text-justify ${
                  isHighlighted && highlightedFinding
                    ? highlightBlockClass(highlightedFinding.severity)
                    : ""
                }`}
              >
                <p className="whitespace-pre-wrap">
                  {highlightedFinding
                    ? renderHighlightedText(p, match, idx, highlightedFinding.severity)
                    : p}
                </p>
              </div>
            );
          })
        ) : (
          DEFAULT_PARAGRAPHS.map((para, idx) => {
            const isHighlighted = Boolean(highlightedFinding && match?.paragraphIndex === idx);
            // Match was computed against label+text; re-resolve against body for exact splits
            let bodyMatch: HighlightMatch | null = null;
            if (isHighlighted && highlightedFinding && match) {
              if (match.kind === "exact") {
                const range = findExactRange(para.text, highlightedFinding.matchedText);
                bodyMatch = range
                  ? { kind: "exact", paragraphIndex: idx, start: range.start, end: range.end }
                  : { kind: "fuzzy", paragraphIndex: idx };
              } else {
                bodyMatch = match;
              }
            }

            return (
              <div
                key={para.id}
                ref={isHighlighted ? highlightRef : undefined}
                className={`mb-7 ${
                  isHighlighted && highlightedFinding
                    ? highlightBlockClass(highlightedFinding.severity)
                    : ""
                }`}
              >
                {para.type === "header" && (
                  <div className="text-center mb-10 pb-8 border-b-2 border-[#1a1a1a]">
                    {para.text.split("\n").map((line, i) => (
                      <p
                        key={i}
                        className={
                          i < 2
                            ? "font-bold text-base uppercase tracking-widest"
                            : "text-sm text-[#374151]"
                        }
                      >
                        {line}
                      </p>
                    ))}
                  </div>
                )}
                {para.type === "section" && (
                  <div className="mb-4">
                    {para.label && (
                      <p className="font-bold uppercase mb-2">{para.label}</p>
                    )}
                    <p>
                      {highlightedFinding
                        ? renderHighlightedText(
                            para.text,
                            bodyMatch,
                            idx,
                            highlightedFinding.severity
                          )
                        : para.text}
                    </p>
                  </div>
                )}
                {(para.type === "subject" || para.type === "filler") && (
                  <p className={para.type === "subject" ? "mb-6 font-medium" : "mb-4"}>
                    {highlightedFinding
                      ? renderHighlightedText(
                          para.text,
                          bodyMatch,
                          idx,
                          highlightedFinding.severity
                        )
                      : para.text}
                  </p>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ─── SummaryBar ───────────────────────────────────────────────────────────────

function SummaryBar({ findings }: { findings: Finding[] }) {
  const high = findings.filter((f) => f.severity === "high").length;
  const med = findings.filter((f) => f.severity === "medium").length;
  const low = findings.filter((f) => f.severity === "low").length;
  const total = findings.length;

  return (
    <div className="grid grid-cols-4 gap-3 p-4 border-b border-[#E5E7EB] bg-white flex-shrink-0">
      {[
        { label: "Total Findings", value: total, icon: BarChart3, color: "text-[#374151]", bg: "bg-[#F9FAFB]", border: "border-[#E5E7EB]" },
        { label: "High Severity", value: high, icon: AlertCircle, color: "text-red-600", bg: "bg-red-50", border: "border-red-100" },
        { label: "Medium Severity", value: med, icon: AlertTriangle, color: "text-amber-600", bg: "bg-amber-50", border: "border-amber-100" },
        { label: "Low Severity", value: low, icon: Info, color: "text-blue-600", bg: "bg-blue-50", border: "border-blue-100" },
      ].map(({ label, value, icon: Icon, color, bg, border }) => (
        <div key={label} className={`rounded-xl p-3 border ${bg} ${border} flex items-center gap-3`}>
          <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center flex-shrink-0 border ${border}`}>
            <Icon size={15} className={color} />
          </div>
          <div>
            <p className={`text-xl font-bold ${color} leading-none mb-0.5`}>{value}</p>
            <p className="text-xs text-[#9CA3AF] font-medium">{label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── ProcessingView ───────────────────────────────────────────────────────────

function ProcessingView({
  draftText,
  fileName,
  onComplete,
  onError,
}: {
  draftText: string;
  fileName: string;
  onComplete: (result: ConflictFinding) => void;
  onError: () => void;
}) {
  const [currentStep, setCurrentStep] = useState(0);
  const [conflictResult, setConflictResult] = useState<ConflictFinding | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const runAnalysis = useCallback(() => {
    setErrorMsg(null);
    setCurrentStep(0);
    setDone(false);

    // Call real FastAPI backend POST /reasoning/conflict
    checkConflict(draftText)
      .then((result) => {
        setConflictResult(result);
        setCurrentStep(PROCESSING_STEPS.length - 1);
        setDone(true);
      })
      .catch((err: ApiError | Error) => {
        setErrorMsg(err.message || "Failed to connect to conflict reasoning API.");
      });
  }, [draftText]);

  useEffect(() => {
    runAnalysis();
  }, [runAnalysis]);

  // Visual step progress timer
  useEffect(() => {
    if (!errorMsg && currentStep < PROCESSING_STEPS.length - 1) {
      const t = setTimeout(() => setCurrentStep((s) => s + 1), 900);
      return () => clearTimeout(t);
    }
  }, [currentStep, errorMsg]);

  if (errorMsg) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#F8FAFC]">
        <div className="w-full max-w-md bg-white rounded-2xl border border-red-200 shadow-lg p-8 text-center">
          <div className="w-12 h-12 rounded-2xl bg-red-50 text-red-600 flex items-center justify-center mx-auto mb-4 border border-red-100">
            <AlertCircle size={24} />
          </div>
          <h2 className="text-base font-semibold text-[#111827] mb-2">
            Conflict Analysis Failed
          </h2>
          <p className="text-xs text-[#6B7280] mb-6 leading-relaxed bg-red-50 p-3 rounded-xl border border-red-100 font-mono text-left overflow-x-auto">
            {errorMsg}
          </p>
          <div className="flex gap-3">
            <button
              onClick={onError}
              className="flex-1 py-2.5 rounded-xl border border-[#E5E7EB] text-sm font-semibold text-[#374151] hover:bg-[#F9FAFB]"
            >
              Back to Upload
            </button>
            <button
              onClick={runAnalysis}
              className="flex-1 py-2.5 rounded-xl bg-[#2563EB] text-white text-sm font-semibold hover:bg-[#1D4ED8]"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex items-center justify-center bg-[#F8FAFC]">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl border border-[#E5E7EB] shadow-sm overflow-hidden">
          <div className="px-8 pt-8 pb-6 border-b border-[#F3F4F6]">
            <div className="flex items-center gap-3 mb-1">
              <div className="w-10 h-10 rounded-xl bg-[#EFF6FF] flex items-center justify-center">
                <Shield size={20} className="text-[#2563EB]" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-[#111827]">
                  Analysing Resolution for Conflicts
                </h2>
                <p className="text-xs text-[#9CA3AF] mt-0.5 font-mono">
                  {fileName}
                </p>
              </div>
            </div>
          </div>

          <div className="px-8 py-6 space-y-5">
            {PROCESSING_STEPS.map((step, idx) => {
              const Icon = step.icon;
              const isStepDone = idx < currentStep || (idx === currentStep && done);
              const isActive = idx === currentStep && !done;
              return (
                <div key={step.id} className="flex items-start gap-3.5">
                  <div
                    className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 transition-all duration-500 ${
                      isStepDone
                        ? "bg-[#F0FDF4] text-[#22C55E]"
                        : isActive
                        ? "bg-[#EFF6FF] text-[#2563EB]"
                        : "bg-[#F9FAFB] text-[#D1D5DB]"
                    }`}
                  >
                    {isActive ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Icon size={14} />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <span
                        className={`text-sm font-medium transition-colors duration-300 ${
                          isStepDone
                            ? "text-[#22C55E]"
                            : isActive
                            ? "text-[#111827]"
                            : "text-[#D1D5DB]"
                        }`}
                      >
                        {step.label}
                      </span>
                      {isStepDone && (
                        <CheckCircle2 size={13} className="text-[#22C55E]" />
                      )}
                      {isActive && (
                        <span className="text-xs text-[#2563EB] font-medium">
                          Running
                        </span>
                      )}
                    </div>
                    <p
                      className={`text-xs transition-colors duration-300 ${
                        isStepDone ? "text-[#22C55E]/70" : isActive ? "text-[#6B7280]" : "text-[#E5E7EB]"
                      }`}
                    >
                      {step.sub}
                    </p>
                    <div className="h-1 bg-[#F3F4F6] rounded-full overflow-hidden mt-2">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${
                          isStepDone ? "bg-[#22C55E]" : isActive ? "bg-[#2563EB]" : ""
                        }`}
                        style={{ width: isStepDone ? "100%" : isActive ? "55%" : "0%" }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {done && conflictResult && (
            <div className="px-8 pb-8">
              <button
                onClick={() => onComplete(conflictResult)}
                className="w-full py-3 rounded-xl bg-[#2563EB] text-white text-sm font-semibold hover:bg-[#1D4ED8] active:bg-[#1E40AF] transition-all duration-200 flex items-center justify-center gap-2 shadow-sm"
              >
                <Eye size={15} />
                View Review Findings
                <ArrowRight size={14} />
              </button>
            </div>
          )}
        </div>

        <p className="text-xs text-[#9CA3AF] text-center mt-4">
          Cross-referencing statutory database & Neo4j graph · Powered by FastAPI Q&A Reasoning Engine
        </p>
      </div>
    </div>
  );
}

// ─── UploadCard ───────────────────────────────────────────────────────────────

function UploadCard({
  onUpload,
}: {
  onUpload: (draftText: string, fileName: string) => void;
}) {
  const [mode, setMode] = useState<"file" | "paste">("file");
  const [dragging, setDragging] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const [fileText, setFileText] = useState<string>("");
  const [pastedText, setPastedText] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const processFile = useCallback((file: File) => {
    setFileName(file.name);
    // PDF text extraction isn't natively built-in without heavy dependencies;
    // for now we attempt FileReader text extraction or fallback to document text wrapper.
    if (file.name.endsWith(".pdf") || file.type.includes("pdf")) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        if (text && text.length > 50 && !text.includes("\u0000")) {
          setFileText(text);
        } else {
          setFileText(
            `[PDF Document: ${file.name}]\n\n` + SAMPLE_DRAFT_TEXT
          );
        }
      };
      reader.readAsText(file);
    } else {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = (e.target?.result as string) || SAMPLE_DRAFT_TEXT;
        setFileText(text);
      };
      reader.readAsText(file);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        processFile(e.dataTransfer.files[0]);
      } else {
        setFileName("Draft_Resolution_2024.txt");
        setFileText(SAMPLE_DRAFT_TEXT);
      }
    },
    [processFile]
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const handleAnalyse = () => {
    if (mode === "paste") {
      const textToUse = pastedText.trim() || SAMPLE_DRAFT_TEXT;
      onUpload(textToUse, "Pasted_Draft_Resolution.txt");
    } else {
      const textToUse = fileText.trim() || SAMPLE_DRAFT_TEXT;
      const nameToUse = fileName || "National_Green_Infrastructure_Resolution_2024.pdf";
      onUpload(textToUse, nameToUse);
    }
  };

  return (
    <div className="px-6 pt-6">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        className="hidden"
        accept=".txt,.pdf,.doc,.docx"
      />

      {/* Mode selection tabs */}
      <div className="flex items-center gap-2 mb-3">
        <button
          onClick={() => setMode("file")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
            mode === "file"
              ? "bg-[#2563EB] text-white"
              : "bg-white text-[#6B7280] border border-[#E5E7EB] hover:bg-[#F9FAFB]"
          }`}
        >
          <Upload size={12} />
          Upload Document File
        </button>
        <button
          onClick={() => setMode("paste")}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
            mode === "paste"
              ? "bg-[#2563EB] text-white"
              : "bg-white text-[#6B7280] border border-[#E5E7EB] hover:bg-[#F9FAFB]"
          }`}
        >
          <FileCode size={12} />
          Paste Draft GR Text
        </button>
      </div>

      {mode === "paste" ? (
        <div className="bg-white rounded-2xl border border-[#E5E7EB] p-5 shadow-sm">
          <label className="block text-xs font-semibold text-[#111827] mb-2">
            Paste Draft Resolution Text for Legal Conflict Analysis
          </label>
          <textarea
            value={pastedText}
            onChange={(e) => setPastedText(e.target.value)}
            placeholder="Paste draft GR sections here (e.g. Section 4.2 exclusive jurisdiction)..."
            rows={5}
            className="w-full text-xs font-mono p-3 bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl text-[#111827] focus:outline-none focus:ring-2 focus:ring-[#2563EB]/20 focus:border-[#2563EB] mb-3"
          />
          <div className="flex items-center justify-between">
            <button
              onClick={() => setPastedText(SAMPLE_DRAFT_TEXT)}
              className="text-xs text-[#2563EB] font-medium hover:underline"
            >
              Load Sample Conflicts Draft
            </button>
            <button
              onClick={handleAnalyse}
              className="px-5 py-2.5 rounded-xl bg-[#2563EB] text-white text-sm font-semibold hover:bg-[#1D4ED8] transition-colors flex items-center gap-2"
            >
              <Shield size={14} />
              Analyse Draft Text
            </button>
          </div>
        </div>
      ) : (
        <div
          className={`rounded-2xl border-2 border-dashed transition-all duration-200 ${
            dragging
              ? "border-[#2563EB] bg-[#EFF6FF] scale-[1.005]"
              : fileName
              ? "border-[#22C55E] bg-[#F0FDF4]"
              : "border-[#E5E7EB] bg-white hover:border-[#BFDBFE] hover:bg-[#F8FAFC]"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          {fileName ? (
            <div className="flex items-center justify-between px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-[#DCFCE7] flex items-center justify-center">
                  <FileText size={18} className="text-[#22C55E]" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-[#111827]">{fileName}</p>
                  <p className="text-xs text-[#6B7280] mt-0.5">
                    {fileText.length > 0 ? `${fileText.length} characters` : "Document text ready for analysis"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5 text-xs font-semibold text-[#22C55E]">
                  <CheckCircle2 size={13} /> Loaded
                </span>
                <button
                  onClick={handleAnalyse}
                  className="px-4 py-2.5 rounded-xl bg-[#2563EB] text-white text-sm font-semibold hover:bg-[#1D4ED8] transition-colors flex items-center gap-2"
                >
                  <Shield size={14} />
                  Analyse Document
                </button>
                <button
                  onClick={() => {
                    setFileName(null);
                    setFileText("");
                  }}
                  className="p-2 rounded-xl hover:bg-[#F3F4F6] text-[#9CA3AF] hover:text-[#374151] transition-colors"
                >
                  <X size={15} />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-5 px-7 py-5">
              <div className="w-11 h-11 rounded-2xl bg-[#EFF6FF] flex items-center justify-center flex-shrink-0">
                <Upload size={21} className="text-[#2563EB]" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-[#111827] mb-0.5">
                  Upload Government Resolution Document
                </p>
                <p className="text-xs text-[#9CA3AF]">
                  Drag & drop your file here, or{" "}
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="text-[#2563EB] font-semibold hover:underline"
                  >
                    browse files
                  </button>
                  {"  ·  "}TXT, PDF, DOCX — up to 50 MB
                </p>
              </div>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="px-4 py-2.5 rounded-xl border border-[#E5E7EB] text-sm font-semibold text-[#374151] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors flex items-center gap-2 whitespace-nowrap"
              >
                <Upload size={14} />
                Browse File
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [phase, setPhase] = useState<Phase>("upload");
  const [draftText, setDraftText] = useState<string>(SAMPLE_DRAFT_TEXT);
  const [fileName, setFileName] = useState<string>("National_Green_Infrastructure_Resolution_2024.pdf");
  const [conflictResult, setConflictResult] = useState<ConflictFinding | null>(null);

  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [scrollKey, setScrollKey] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [notifOpen, setNotifOpen] = useState(false);
  const [filterSeverity, setFilterSeverity] = useState<Severity | "all">("all");
  const [bookmarks, setBookmarks] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<{ checked: boolean; ok: boolean; msg?: string }>({
    checked: false,
    ok: true,
  });

  // Non-blocking initial health check on app load
  useEffect(() => {
    checkHealth()
      .then((res) => {
        setBackendStatus({ checked: true, ok: res.db !== false });
      })
      .catch((err: Error) => {
        setBackendStatus({
          checked: true,
          ok: false,
          msg: "FastAPI Backend is unreachable at http://localhost:8000. Ensure uvicorn server is running.",
        });
      });
  }, []);

  const showToast = (msg: string) => {
    setToast(msg);
  };

  const handleStartUpload = (text: string, name: string) => {
    setDraftText(text);
    setFileName(name);
    setPhase("processing");
  };

  const handleProcessingComplete = (result: ConflictFinding) => {
    setConflictResult(result);
    setPhase("review");
    showToast("Conflict analysis complete");
  };

  const handleFindingClick = (finding: Finding) => {
    if (selectedFinding?.id === finding.id) {
      setSelectedFinding(null);
    } else {
      setSelectedFinding(finding);
    }
  };

  const handleJumpToClause = () => {
    if (!selectedFinding) return;
    setScrollKey((k) => k + 1);
  };

  const toggleBookmark = (id: string) => {
    setBookmarks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        showToast("Bookmark removed");
      } else {
        next.add(id);
        showToast("Finding saved to bookmarks");
      }
      return next;
    });
  };

  // Derive findings from real ConflictFinding response using adapter
  const findings: Finding[] = conflictResult
    ? mapConflictFindingToFindings(conflictResult)
    : [];

  const filteredFindings =
    filterSeverity === "all"
      ? findings
      : findings.filter((f) => f.severity === filterSeverity);

  return (
    <div
      className="h-screen flex flex-col bg-[#F8FAFC] overflow-hidden"
      style={{ fontFamily: "Inter, sans-serif" }}
    >
      {/* Non-blocking health warning banner */}
      {backendStatus.checked && !backendStatus.ok && (
        <div className="bg-amber-500 text-white text-xs font-semibold py-1.5 px-4 text-center flex items-center justify-center gap-2 z-50">
          <AlertTriangle size={13} />
          {backendStatus.msg || "FastAPI backend unreachable"}
        </div>
      )}

      {/* ── Top Navigation ── */}
      <header className="h-14 bg-white border-b border-[#E5E7EB] flex items-center px-5 gap-4 flex-shrink-0 z-30">
        <div className="flex items-center gap-2.5 mr-4">
          <div className="w-7 h-7 rounded-lg bg-[#2563EB] flex items-center justify-center">
            <Shield size={14} className="text-white" />
          </div>
          <div className="flex items-baseline gap-1.5">
            <span className="text-sm font-bold text-[#111827] tracking-tight">
              ResolutionReview
            </span>
            <span className="hidden xl:block text-xs text-[#9CA3AF] font-medium">
              · Government of India
            </span>
          </div>
        </div>

        {/* Global search */}
        <div className="flex-1 max-w-xs">
          <div className="relative">
            <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#9CA3AF]" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search clauses, findings…"
              className="w-full pl-8 pr-4 py-2 text-sm bg-[#F9FAFB] border border-[#E5E7EB] rounded-xl placeholder-[#C4C9D4] text-[#111827] focus:outline-none focus:ring-2 focus:ring-[#2563EB]/20 focus:border-[#2563EB] transition-all"
            />
          </div>
        </div>

        <div className="flex-1" />

        {phase === "review" && (
          <div className="hidden lg:flex items-center gap-2 text-xs text-[#6B7280] border-r border-[#E5E7EB] pr-4 mr-1">
            <TrendingUp size={13} className="text-[#22C55E]" />
            <span>
              <span className="font-semibold text-[#111827]">{findings.length}</span> findings · analyzed{" "}
              <span className="font-semibold text-[#111827]">
                {new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
              </span>
            </span>
          </div>
        )}

        <div className="flex items-center gap-2">
          {phase === "review" && (
            <>
              <button
                onClick={() => showToast("Exporting resolution review summary...")}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-xs font-semibold text-[#374151] hover:bg-[#F9FAFB] transition-colors"
              >
                <Download size={12} />
                Export
              </button>
              <button
                onClick={() => {
                  setPhase("upload");
                  setSelectedFinding(null);
                  setConflictResult(null);
                  setFilterSeverity("all");
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-xs font-semibold text-[#374151] hover:bg-[#F9FAFB] transition-colors"
              >
                <RefreshCw size={12} />
                New Review
              </button>
            </>
          )}

          {/* Notifications */}
          <div className="relative">
            <button
              onClick={() => setNotifOpen((o) => !o)}
              className="relative p-2 rounded-xl hover:bg-[#F3F4F6] text-[#6B7280] hover:text-[#111827] transition-colors"
            >
              <Bell size={17} />
              {phase === "review" && (
                <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-[#EF4444] rounded-full border-2 border-white" />
              )}
            </button>
            {notifOpen && (
              <div className="absolute right-0 top-11 w-80 bg-white rounded-2xl border border-[#E5E7EB] shadow-xl z-50 overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E7EB]">
                  <p className="text-sm font-semibold text-[#111827]">Notifications</p>
                  <span className="text-xs text-[#9CA3AF]">
                    {phase === "review" ? "1 unread" : "0 unread"}
                  </span>
                </div>
                <div className="p-2">
                  {phase === "review" ? (
                    <div className="px-3 py-3 rounded-xl bg-[#EFF6FF] border border-[#BFDBFE] mb-1">
                      <div className="flex items-start gap-2.5">
                        <div className="w-6 h-6 rounded-lg bg-[#2563EB] flex items-center justify-center flex-shrink-0 mt-0.5">
                          <CheckCircle2 size={12} className="text-white" />
                        </div>
                        <div>
                          <p className="text-xs font-semibold text-[#111827] mb-0.5">
                            Conflict Analysis Complete
                          </p>
                          <p className="text-xs text-[#6B7280] leading-relaxed">
                            {findings.length} finding(s) detected via FastAPI reasoning engine.
                          </p>
                          <p className="text-xs text-[#9CA3AF] mt-1.5 flex items-center gap-1">
                            <Clock size={10} /> Just now
                          </p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-[#9CA3AF] text-center py-6">
                      No new notifications
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* User profile */}
          <button className="flex items-center gap-2 pl-2 pr-3 py-1.5 rounded-xl hover:bg-[#F3F4F6] transition-colors">
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-[#2563EB] to-[#7C3AED] flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
              AS
            </div>
            <span className="hidden sm:block text-sm font-medium text-[#374151]">
              Aditi Sharma
            </span>
            <ChevronDown size={13} className="text-[#9CA3AF]" />
          </button>
        </div>
      </header>

      {/* ── Upload Phase ── */}
      {phase === "upload" && (
        <div className="flex-1 overflow-y-auto">
          <UploadCard onUpload={handleStartUpload} />
          <div className="flex flex-col items-center justify-center min-h-[calc(100%-140px)] text-center px-6 py-10">
            <div className="w-14 h-14 rounded-2xl bg-white border border-[#E5E7EB] shadow-sm flex items-center justify-center mb-5">
              <BookOpen size={26} className="text-[#D1D5DB]" />
            </div>
            <h2 className="text-sm font-semibold text-[#374151] mb-1.5">
              Automated Legal Conflict Detection
            </h2>
            <p className="text-sm text-[#9CA3AF] max-w-sm leading-relaxed mb-10">
              Upload a Government Resolution document or paste text to cross-reference against 1,840+ statutory provisions and citation graphs.
            </p>
            <div className="grid grid-cols-3 gap-4 max-w-xl w-full">
              {[
                { icon: Shield, label: "Conflict Detection", desc: "Identifies jurisdiction, financial, and legal conflicts against statutory provisions" },
                { icon: BarChart3, label: "Severity Analysis", desc: "Findings ranked High / Medium / Low with LLM confidence metrics" },
                { icon: CheckCircle2, label: "Actionable Guidance", desc: "Cross-references affected GRs and provides structured legal reasoning" },
              ].map(({ icon: Icon, label, desc }) => (
                <div key={label} className="bg-white rounded-2xl border border-[#E5E7EB] p-5 text-left hover:shadow-md hover:-translate-y-0.5 transition-all duration-200">
                  <div className="w-8 h-8 rounded-xl bg-[#EFF6FF] flex items-center justify-center mb-4">
                    <Icon size={16} className="text-[#2563EB]" />
                  </div>
                  <p className="text-xs font-semibold text-[#111827] mb-1.5">{label}</p>
                  <p className="text-xs text-[#9CA3AF] leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Processing Phase ── */}
      {phase === "processing" && (
        <ProcessingView
          draftText={draftText}
          fileName={fileName}
          onComplete={handleProcessingComplete}
          onError={() => setPhase("upload")}
        />
      )}

      {/* ── Review Phase ── */}
      {phase === "review" && (
        <>
          {/* File breadcrumb */}
          <div className="bg-white border-b border-[#E5E7EB] px-6 py-2.5 flex items-center gap-3 flex-shrink-0">
            <div className="flex items-center gap-2 text-xs text-[#6B7280]">
              <FileText size={12} className="text-[#9CA3AF]" />
              <span className="font-medium text-[#374151] font-mono">
                {fileName}
              </span>
              <span className="text-[#D1D5DB]">·</span>
              <span>{draftText.length} characters</span>
              <span className="text-[#D1D5DB]">·</span>
              <span className="text-[#22C55E] font-medium flex items-center gap-1">
                <CheckCircle2 size={11} />
                Analysis complete
              </span>
            </div>
          </div>

          {/* Main workspace */}
          <div className="flex-1 flex overflow-hidden">
            {/* Document pane — 65% */}
            <div className="flex flex-col" style={{ width: "65%" }}>
              {/* Viewer toolbar */}
              <div className="bg-[#3C3F41] flex items-center gap-2 px-4 py-2.5 flex-shrink-0">
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setZoom((z) => Math.max(50, z - 10))}
                    title="Zoom out"
                    className="p-1.5 rounded-lg hover:bg-white/10 text-[#C4C9D4] hover:text-white transition-colors"
                  >
                    <ZoomOut size={14} />
                  </button>
                  <span className="text-xs font-mono text-[#C4C9D4] w-10 text-center select-none">
                    {zoom}%
                  </span>
                  <button
                    onClick={() => setZoom((z) => Math.min(200, z + 10))}
                    title="Zoom in"
                    className="p-1.5 rounded-lg hover:bg-white/10 text-[#C4C9D4] hover:text-white transition-colors"
                  >
                    <ZoomIn size={14} />
                  </button>
                  <button
                    onClick={() => setZoom(100)}
                    className="text-xs text-[#6B7280] hover:text-[#C4C9D4] ml-1 transition-colors"
                    title="Reset zoom"
                  >
                    Reset
                  </button>
                </div>

                <div className="w-px h-4 bg-white/15 mx-1" />

                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    className="p-1.5 rounded-lg hover:bg-white/10 text-[#C4C9D4] hover:text-white transition-colors"
                  >
                    <ChevronLeft size={14} />
                  </button>
                  <span className="text-xs font-mono text-[#C4C9D4] select-none">
                    {currentPage} / 1
                  </span>
                  <button
                    onClick={() => setCurrentPage((p) => Math.min(1, p + 1))}
                    className="p-1.5 rounded-lg hover:bg-white/10 text-[#C4C9D4] hover:text-white transition-colors"
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>

                <div className="w-px h-4 bg-white/15 mx-1" />

                <div className="relative max-w-[180px]">
                  <Search size={11} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#6B7280]" />
                  <input
                    placeholder="Find in document…"
                    className="w-full pl-7 pr-3 py-1 text-xs bg-white/8 rounded-lg text-[#E5E7EB] placeholder-[#6B7280] border border-white/10 focus:outline-none focus:ring-1 focus:ring-white/25"
                  />
                </div>

                <div className="ml-auto">
                  {selectedFinding ? (
                    <span className="flex items-center gap-1.5 text-xs font-medium text-amber-400">
                      <AlertTriangle size={12} />
                      Highlighting {selectedFinding.clauseNumber}
                    </span>
                  ) : (
                    <span className="text-xs text-[#6B7280]">
                      Select a finding to inspect
                    </span>
                  )}
                </div>
              </div>

              <DocumentViewer
                draftText={draftText}
                highlightedFinding={
                  selectedFinding
                    ? {
                        id: selectedFinding.id,
                        matchedText: selectedFinding.summary,
                        severity: selectedFinding.severity,
                      }
                    : null
                }
                zoom={zoom}
                scrollKey={scrollKey}
              />
            </div>

            {/* Findings panel — 35% */}
            <div
              className="flex flex-col border-l border-[#E5E7EB] bg-[#F8FAFC] overflow-hidden"
              style={{ width: "35%" }}
            >
              {/* Summary stats */}
              <SummaryBar findings={findings} />

              {/* Panel header */}
              <div className="px-4 pt-4 pb-3 border-b border-[#E5E7EB] bg-white flex-shrink-0">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-semibold text-[#111827]">
                    Conflict Findings
                  </h2>
                  <span className="text-xs text-[#9CA3AF] bg-[#F3F4F6] px-2 py-0.5 rounded-md font-medium">
                    {filteredFindings.length} shown
                  </span>
                </div>

                {/* Filter tabs */}
                <div className="flex gap-1.5">
                  {(["all", "high", "medium", "low"] as const).map((s) => (
                    <button
                      key={s}
                      onClick={() => setFilterSeverity(s)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 ${
                        filterSeverity === s
                          ? s === "all"
                            ? "bg-[#111827] text-white"
                            : s === "high"
                            ? "bg-red-600 text-white"
                            : s === "medium"
                            ? "bg-amber-500 text-white"
                            : "bg-blue-600 text-white"
                          : "text-[#6B7280] hover:bg-[#F3F4F6]"
                      }`}
                    >
                      {s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Findings list */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {conflictResult && !conflictResult.conflicting ? (
                  <div className="text-center py-12 px-4 bg-white rounded-2xl border border-green-200">
                    <div className="w-12 h-12 rounded-2xl bg-green-50 text-green-600 flex items-center justify-center mx-auto mb-3 border border-green-100">
                      <CheckCircle2 size={24} />
                    </div>
                    <h3 className="text-sm font-semibold text-[#111827] mb-1">
                      No Conflicts Detected
                    </h3>
                    <p className="text-xs text-[#6B7280] leading-relaxed">
                      {conflictResult.explanation ||
                        "The draft resolution text was cross-referenced against the statutory database and no direct policy contradictions were identified."}
                    </p>
                  </div>
                ) : (
                  filteredFindings.map((finding) => (
                    <FindingCard
                      key={finding.id}
                      finding={finding}
                      active={selectedFinding?.id === finding.id}
                      bookmarked={bookmarks.has(finding.id)}
                      onClick={() => handleFindingClick(finding)}
                      onBookmark={(e) => {
                        e.stopPropagation();
                        toggleBookmark(finding.id);
                      }}
                    />
                  ))
                )}

                {conflictResult?.conflicting && filteredFindings.length === 0 && (
                  <div className="text-center py-10">
                    <p className="text-sm text-[#9CA3AF]">No findings at this severity level.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Inspector drawer */}
      <InspectorDrawer
        finding={selectedFinding}
        bookmarked={selectedFinding ? bookmarks.has(selectedFinding.id) : false}
        onClose={() => setSelectedFinding(null)}
        onBookmark={() => selectedFinding && toggleBookmark(selectedFinding.id)}
        onJump={handleJumpToClause}
        onFlag={() => showToast("Finding flagged for legal review")}
      />

      {/* Notif backdrop */}
      {notifOpen && (
        <div className="fixed inset-0 z-40" onClick={() => setNotifOpen(false)} />
      )}

      {/* Toast */}
      {toast && <Toast message={toast} onDone={() => setToast(null)} />}
    </div>
  );
}
