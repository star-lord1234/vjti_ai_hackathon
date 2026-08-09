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
  Languages,
  LayoutTemplate,
  Save,
  Pencil,
  History,
  Share2,
  ExternalLink,
} from "lucide-react";
import { DraftChatWidget } from "./components/DraftChatWidget";
import { VersionHistoryModal } from "./components/VersionHistoryModal";
import { RoleProvider, useUserRole } from "./components/RoleContext";
import { HeaderBar } from "./components/HeaderBar";
import { DepartmentForumView } from "./components/DepartmentForumView";
import { SharedGRDetailView } from "./components/SharedGRDetailView";
import { PdfTemplateEditor } from "./components/PdfTemplateEditor";
import { OriginalGRViewerModal } from "./components/OriginalGRViewerModal";
import maharashtraSeal from "./components/figma/Seal_of_Maharashtra.svg";
import {
  checkHealth,
  analyzeDraft,
  analyzeDraftStream,
  AnalysisProgressEvent,
  createDraft,
  saveDraft,
  saveAndRecheckDraft,
  shareDraftWithDepartment,
  ConflictFinding,
  GlossaryCheckSection,
  GlossaryFinding,
  DraftAnalysisResponse,
  DraftSaveResponse,
  DraftRecheckResponse,
  ClauseDiffResult,
  DraftStatus,
  TemplateCheckSection,
  ApiError,
} from "../lib/api";
import {
  mapConflictFindingToFindings,
  mapTemplateFindingsToFindings,
  Finding,
  Severity,
} from "../lib/adapters";
import {
  MAHARASHTRA_SAMPLE_DRAFT,
  MAHARASHTRA_SAMPLE_FILENAME,
} from "../lib/sampleDraft";
import { extractTextFromPdf, isPdfFile } from "../lib/pdf";
import {
  GR_TEMPLATE_RULES,
  GR_TEMPLATE_SCORING_NOTE,
} from "../lib/grTemplateRules";

// ─── Types ────────────────────────────────────────────────────────────────────

type Phase = "upload" | "processing" | "review" | "dept_forum" | "shared_detail" | "pdf_template";


// ─── Draft status badge ───────────────────────────────────────────────────────

const DRAFT_STATUS_LABELS: Record<DraftStatus, string> = {
  draft: "Draft",
  ready_for_approval: "Ready for approval",
  approved: "Approved",
};

function DraftStatusBadge({ status }: { status: DraftStatus }) {
  const styles: Record<DraftStatus, string> = {
    draft: "bg-[#F3F4F6] text-[#374151] border-[#E5E7EB]",
    ready_for_approval: "bg-green-50 text-green-700 border-green-200",
    approved: "bg-blue-50 text-blue-700 border-blue-200",
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-md border text-[11px] font-semibold uppercase tracking-wide ${styles[status]}`}
    >
      {DRAFT_STATUS_LABELS[status]}
    </span>
  );
}

// ─── Draft editor (explicit save workflow) ────────────────────────────────────

function DraftEditor({
  value,
  onChange,
  isPreview,
  draftText,
  highlightedFinding,
  zoom,
  scrollTarget,
  scrollKey,
}: {
  value: string;
  onChange: (text: string) => void;
  isPreview: boolean;
  draftText: string;
  highlightedFinding: HighlightableFinding | null;
  zoom: number;
  scrollTarget?: string | number;
  scrollKey?: number;
}) {
  if (isPreview) {
    return (
      <DocumentViewer
        draftText={draftText}
        highlightedFinding={highlightedFinding}
        zoom={zoom}
        scrollTarget={scrollTarget}
        scrollKey={scrollKey}
      />
    );
  }

  return (
    <div className="flex-1 overflow-hidden bg-[#F8FAFC] p-4">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-full min-h-[calc(100vh-220px)] resize-none rounded-xl border border-[#E5E7EB] bg-white p-6 text-sm leading-relaxed text-[#111827] shadow-sm focus:outline-none focus:ring-2 focus:ring-[#2563EB]/30 font-mono"
        spellCheck={false}
        aria-label="Editable draft text"
      />
    </div>
  );
}

// ─── Default Document Fallback (review UI only when draft is empty) ─────────

const DEFAULT_PARAGRAPHS: DocPara[] = [
  {
    id: "header",
    type: "header",
    text: "महाराष्ट्र शासन\nउच्च व तंत्र शिक्षण विभाग\n\nशासन निर्णय\n\nक्र. ITI-2024/CR-102/EDU-1",
  },
  {
    id: "subject",
    type: "subject",
    text: "विषय: आयटीआय शिष्यवृत्ती व शुल्क रचनेचे एकत्रीकरण — अंमलबजावणी मार्गदर्शक तत्त्वे",
  },
  {
    id: "s4",
    type: "section",
    label: "कलम 4 — अधिकारक्षेत्र",
    highlight: "f-1",
    highlightPhrase: "EXCLUSIVE JURISDICTION",
    text: "4.1 संबंधित विभाग हा विषयाचा नोडल विभाग राहील.\n\n4.2 राज्य अधिकारी पर्यावरणीय प्रभाव मूल्यांकनासाठी EXCLUSIVE JURISDICTION बाळगतील.",
  },
  {
    id: "s7",
    type: "section",
    label: "कलम 7 — आर्थिक अधिकार",
    highlight: "f-2",
    highlightPhrase: "₹85,00,00,000",
    text: "7.1 सक्षम प्राधिकरणास रुपये पंच्याऐंशी लाख (₹85,00,00,000) पर्यंतच्या मर्यादेने खरेदी मंजूर करण्याचा अधिकार देण्यात येतो.",
  },
];

const PROCESSING_STEPS = [
  {
    id: "read",
    label: "Reading Document",
    sub: "Parsing document structure and metadata",
    icon: BookOpen,
  },
  {
    id: "extract",
    label: "Extracting Clauses",
    sub: "Identifying draft resolution provisions",
    icon: FileText,
  },
  {
    id: "detect",
    label: "Detecting Conflicts",
    sub: "Cross-referencing statutory database & Neo4j graph",
    icon: Shield,
  },
  {
    id: "analyse",
    label: "Generating Analysis",
    sub: "Producing severity assessments",
    icon: BarChart3,
  },
  {
    id: "complete",
    label: "Review Complete",
    sub: "Findings ready for review",
    icon: CheckCircle2,
  },
];

interface DocPara {
  id: string;
  type: "header" | "subject" | "section" | "filler";
  label?: string;
  text: string;
  highlight?: string;
  highlightPhrase?: string;
}

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

function SeverityBadge({
  severity,
  size = "sm",
}: {
  severity: Severity;
  size?: "sm" | "md";
}) {
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

function looksLikeCanonicalGrNumber(value?: string | null): boolean {
  if (!value) return false;
  const trimmed = value.trim();
  if (!trimmed) return false;
  return !/[\/\-]/.test(trimmed) && !/[A-Za-z]/.test(trimmed);
}

function getDisplayGrReference(finding: Finding) {
  const explicitNumber = finding.corpusGrNumber?.trim();
  const fallbackLabel = finding.corpusGrLabel?.trim();

  if (!explicitNumber) {
    return { number: undefined, label: fallbackLabel || undefined };
  }

  if (looksLikeCanonicalGrNumber(explicitNumber)) {
    return { number: undefined, label: fallbackLabel || explicitNumber };
  }

  return { number: explicitNumber, label: fallbackLabel || undefined };
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
  const displayGr = getDisplayGrReference(finding);

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

        <p className="text-sm font-medium text-[#111827] leading-snug mb-2">
          {finding.summary}
        </p>

        {finding.corpusExcerpt && (
          <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50/80 px-3 py-2">
            <div className="flex items-center justify-between gap-2 mb-1">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-800">
                Existing GR
              </p>
              {displayGr.number ? (
                <span
                  className="text-[9px] font-mono text-amber-700 bg-amber-100 px-2 py-0.5 rounded-md border border-amber-200 max-w-[170px] truncate"
                  title={displayGr.number}
                >
                  {displayGr.number}
                </span>
              ) : displayGr.label ? (
                <span
                  className="text-[9px] text-amber-700 bg-amber-100 px-2 py-0.5 rounded-md border border-amber-200 max-w-[170px] truncate"
                  title={displayGr.label}
                >
                  {displayGr.label}
                </span>
              ) : null}
            </div>
            {finding.corpusGrLabel && displayGr.number && (
              <p className="text-[10px] text-amber-600 mb-1">
                {finding.corpusGrLabel}
              </p>
            )}
            <p className="text-xs text-amber-950 leading-relaxed line-clamp-2">
              {finding.corpusExcerpt}
            </p>
          </div>
        )}

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
  onOpenCitedGR,
}: {
  finding: Finding | null;
  bookmarked: boolean;
  onClose: () => void;
  onBookmark: () => void;
  onJump: () => void;
  onFlag: () => void;
  onOpenCitedGR?: (grRef: string) => void;
}) {
  const cfg = finding ? severityConfig(finding.severity) : null;
  const Icon = cfg?.icon ?? Info;
  const displayGr = finding
    ? getDisplayGrReference(finding)
    : { number: undefined, label: undefined };
  const conflictTypeLabel = finding?.conflictType
    ? finding.conflictType.charAt(0).toUpperCase() +
      finding.conflictType.slice(1)
    : undefined;

  return (
    <>
      <div
        className={`fixed inset-0 z-40 transition-opacity duration-300 ${
          finding
            ? "opacity-100 pointer-events-auto"
            : "opacity-0 pointer-events-none"
        }`}
        style={{ background: "transparent" }}
        onClick={finding ? onClose : undefined}
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
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <SeverityBadge severity={finding.severity} size="md" />
                  <span className="text-xs text-[#9CA3AF] font-mono bg-[#F9FAFB] px-2 py-0.5 rounded-md border border-[#E5E7EB]">
                    {finding.clauseNumber}
                  </span>
                  {conflictTypeLabel && (
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-[#475569] bg-slate-100 px-2 py-1 rounded-full border border-slate-200">
                      {conflictTypeLabel}
                    </span>
                  )}
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
                  {
                    label: "Page",
                    value: `Page ${finding.page}`,
                    icon: FileText,
                  },
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
                    <p className="text-xs font-semibold text-[#111827]">
                      {value}
                    </p>
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
                <ArrowRight
                  size={14}
                  className="text-[#9CA3AF] group-hover:text-[#2563EB] transition-colors"
                />
              </button>

              {(finding.draftExcerpt || finding.corpusExcerpt) && (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-5 h-5 rounded-md bg-[#FEF3C7] flex items-center justify-center">
                      <Layers size={11} className="text-amber-700" />
                    </div>
                    <h3 className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">
                      Draft vs Existing GR
                    </h3>
                  </div>
                  <div className="grid grid-cols-1 gap-3">
                    {finding.draftExcerpt && (
                      <div className="rounded-2xl border border-red-200 bg-red-50 p-4">
                        <p className="text-[10px] font-semibold uppercase tracking-wide text-red-700 mb-2">
                          Draft proposes
                        </p>
                        <p className="text-sm text-red-950 leading-relaxed">
                          {finding.draftExcerpt}
                        </p>
                      </div>
                    )}
                    {finding.corpusExcerpt && (
                      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                        <div className="flex items-center justify-between gap-2 mb-2">
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-800">
                            Existing GR provides
                          </p>
                          {displayGr.number ? (
                            <span
                              className="text-[10px] font-mono text-amber-700 bg-amber-100 px-2 py-0.5 rounded-md border border-amber-200 max-w-[180px] truncate"
                              title={displayGr.number}
                            >
                              {displayGr.number}
                            </span>
                          ) : displayGr.label ? (
                            <span
                              className="text-[10px] text-amber-700 bg-amber-100 px-2 py-0.5 rounded-md border border-amber-200 max-w-[180px] truncate"
                              title={displayGr.label}
                            >
                              {displayGr.label}
                            </span>
                          ) : null}
                        </div>
                        {finding.corpusGrLabel && displayGr.number && (
                          <p className="text-[10px] text-amber-600 mb-1.5">
                            {finding.corpusGrLabel}
                          </p>
                        )}
                        <p className="text-sm text-amber-950 leading-relaxed">
                          {finding.corpusExcerpt}
                        </p>
                        <div className="mt-3 pt-2.5 border-t border-amber-200/60 flex items-center justify-between">
                          <span className="text-[10px] text-amber-700 font-medium">Institutional Corpus GR</span>
                          <button
                            onClick={() => onOpenCitedGR?.(displayGr.number || displayGr.label || finding.corpusGrLabel || "")}
                            className="text-[11px] text-amber-900 bg-amber-200/80 hover:bg-amber-300 border border-amber-300 rounded-lg px-2.5 py-1 font-bold flex items-center gap-1 transition-colors shadow-2xs"
                            title="Read the complete original text of this cited GR"
                          >
                            <ExternalLink size={11} />
                            Read Full Original GR ↗
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-5 h-5 rounded-md bg-[#EFF6FF] flex items-center justify-center">
                    <BarChart3 size={11} className="text-[#2563EB]" />
                  </div>
                  <h3 className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">
                    Detailed AI Analysis
                  </h3>
                </div>
                <div
                  className={`rounded-2xl p-4 border ${cfg.border} ${cfg.bg}`}
                >
                  <div className="flex items-start gap-2 mb-2">
                    <Icon
                      size={14}
                      className={`${cfg.color} mt-0.5 flex-shrink-0`}
                    />
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
                <Bookmark
                  size={13}
                  fill={bookmarked ? "currentColor" : "none"}
                />
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
  snippet: string,
): { start: number; end: number } | null {
  const needle = normalizeForMatch(snippet);
  if (!needle) return null;
  const { normalized, normToOrig } = buildNormalizedIndex(original);

  let idx = normalized.indexOf(needle);
  if (idx === -1) {
    // Fall back to case-insensitive match on normalized text
    idx = normalized.toLowerCase().indexOf(needle.toLowerCase());
  }
  if (idx === -1) return null;

  const start = normToOrig[idx];
  const last = normToOrig[idx + needle.length - 1];
  return { start, end: last + 1 };
}

/** Compute token overlap ratio between paragraph and snippet. */
function tokenOverlapRatio(paragraphText: string, snippetText: string): number {
  const normParagraph = normalizeForMatch(paragraphText).toLowerCase();
  const normSnippet = normalizeForMatch(snippetText).toLowerCase();
  const paragraphTokens = new Set(normParagraph.split(/\s+/).filter(Boolean));
  const snippetTokens = normSnippet.split(/\s+/).filter(Boolean);

  if (paragraphTokens.size === 0 || snippetTokens.length === 0) return 0;
  let overlapCount = 0;
  for (const token of snippetTokens) {
    if (paragraphTokens.has(token)) {
      overlapCount++;
    }
  }
  return overlapCount / snippetTokens.length;
}

type HighlightMatch =
  | { kind: "exact"; paragraphIndex: number; start: number; end: number }
  | { kind: "fuzzy"; paragraphIndex: number };

function findHighlightMatch(
  paragraphs: string[],
  snippet: string,
): HighlightMatch | null {
  const normSnippet = normalizeForMatch(snippet);
  if (!normSnippet) return null;

  // 1. Try exact substring match first across all paragraphs
  for (let i = 0; i < paragraphs.length; i++) {
    const range = findExactRange(paragraphs[i], snippet);
    if (range) {
      return {
        kind: "exact",
        paragraphIndex: i,
        start: range.start,
        end: range.end,
      };
    }
  }

  // 2. Fall back to fuzzy match (highest token-overlap ratio)
  let bestIdx = -1;
  let bestScore = 0;
  for (let i = 0; i < paragraphs.length; i++) {
    const score = tokenOverlapRatio(paragraphs[i], snippet);
    if (score > bestScore) {
      bestScore = score;
      bestIdx = i;
    }
  }

  if (bestIdx >= 0 && bestScore > 0) {
    return { kind: "fuzzy", paragraphIndex: bestIdx };
  }
  return null;
}

function highlightMarkClass(severity?: Severity): string {
  switch (severity) {
    case "high":
      return "bg-red-200/90 text-red-950 rounded px-1 py-0.5 font-medium shadow-sm border-b-2 border-red-500 box-decoration-clone";
    case "medium":
      return "bg-amber-200/90 text-amber-950 rounded px-1 py-0.5 font-medium shadow-sm border-b-2 border-amber-500 box-decoration-clone";
    case "low":
    default:
      return "bg-blue-200/90 text-blue-950 rounded px-1 py-0.5 font-medium shadow-sm border-b-2 border-blue-500 box-decoration-clone";
  }
}

function highlightBlockClass(severity?: Severity, fuzzy?: boolean): string {
  // Fuzzy matches: only a subtle left border — no background fill that masks the draft
  if (fuzzy) {
    switch (severity) {
      case "high":
        return "border-l-4 border-red-400 pl-3 transition-all duration-300";
      case "medium":
        return "border-l-4 border-amber-400 pl-3 transition-all duration-300";
      case "low":
      default:
        return "border-l-4 border-blue-400 pl-3 transition-all duration-300";
    }
  }
  // Exact matches: full block highlight
  switch (severity) {
    case "high":
      return "bg-red-50/80 outline outline-2 outline-red-400/70 rounded-xl p-3 -m-3 transition-all duration-300 shadow-sm";
    case "medium":
      return "bg-amber-50/80 outline outline-2 outline-amber-400/70 rounded-xl p-3 -m-3 transition-all duration-300 shadow-sm";
    case "low":
    default:
      return "bg-blue-50/80 outline outline-2 outline-blue-400/70 rounded-xl p-3 -m-3 transition-all duration-300 shadow-sm";
  }
}

/** Generic interface for findings that can be highlighted in DocumentViewer. */
export type HighlightableFinding = {
  id: string;
  matched_text?: string;
  matchedText?: string;
  severity?: Severity;
  location?: string;
};

function renderHighlightedText(
  text: string,
  match: HighlightMatch | null,
  paragraphIndex: number,
  severity?: Severity,
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
  scrollTarget,
  scrollKey = 0,
}: {
  draftText: string;
  highlightedFinding: HighlightableFinding | null;
  zoom: number;
  scrollTarget?: string | number;
  scrollKey?: number;
}) {
  const highlightRef = useRef<HTMLDivElement>(null);

  const paragraphs = draftText
    ? draftText.split(/\n\n+/).filter((b) => b.trim().length > 0)
    : [];

  const defaultTexts = DEFAULT_PARAGRAPHS.map((p) =>
    p.label ? `${p.label}\n${p.text}` : p.text,
  );
  const textsForMatch = paragraphs.length > 0 ? paragraphs : defaultTexts;

  const snippet =
    highlightedFinding?.matched_text || highlightedFinding?.matchedText || "";

  const match = snippet ? findHighlightMatch(textsForMatch, snippet) : null;

  // Scroll matched paragraph into view when the selected finding or scrollTarget changes
  useEffect(() => {
    if (!highlightedFinding?.id && !scrollTarget) return;
    const t = window.setTimeout(() => {
      highlightRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }, 50);
    return () => window.clearTimeout(t);
  }, [highlightedFinding?.id, scrollTarget, scrollKey]);

  return (
    <div
      className="flex-1 overflow-y-auto bg-transparent flex justify-center py-8 px-6"
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
        {paragraphs.length > 0
          ? paragraphs.map((p, idx) => {
              const isHighlighted = Boolean(
                highlightedFinding && match?.paragraphIndex === idx,
              );
              return (
                <div
                  key={idx}
                  ref={isHighlighted ? highlightRef : undefined}
                  className={`mb-6 text-justify ${
                    isHighlighted && highlightedFinding
                      ? highlightBlockClass(
                          highlightedFinding.severity,
                          match?.kind === "fuzzy",
                        )
                      : ""
                  }`}
                >
                  <p className="whitespace-pre-wrap">
                    {highlightedFinding
                      ? renderHighlightedText(
                          p,
                          match,
                          idx,
                          highlightedFinding.severity,
                        )
                      : p}
                  </p>
                </div>
              );
            })
          : DEFAULT_PARAGRAPHS.map((para, idx) => {
              const isHighlighted = Boolean(
                highlightedFinding && match?.paragraphIndex === idx,
              );
              const isFuzzy = isHighlighted && match?.kind === "fuzzy";
              let bodyMatch: HighlightMatch | null = null;
              if (isHighlighted && highlightedFinding && match) {
                if (match.kind === "exact") {
                  const range = findExactRange(para.text, snippet);
                  bodyMatch = range
                    ? {
                        kind: "exact",
                        paragraphIndex: idx,
                        start: range.start,
                        end: range.end,
                      }
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
                      ? highlightBlockClass(
                          highlightedFinding.severity,
                          isFuzzy,
                        )
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
                              highlightedFinding.severity,
                            )
                          : para.text}
                      </p>
                    </div>
                  )}
                  {(para.type === "subject" || para.type === "filler") && (
                    <p
                      className={
                        para.type === "subject" ? "mb-6 font-medium" : "mb-4"
                      }
                    >
                      {highlightedFinding
                        ? renderHighlightedText(
                            para.text,
                            bodyMatch,
                            idx,
                            highlightedFinding.severity,
                          )
                        : para.text}
                    </p>
                  )}
                </div>
              );
            })}
      </div>
    </div>
  );
}

// ─── Template accuracy indicator ──────────────────────────────────────────────

function templateScoreColor(score: number): {
  bar: string;
  text: string;
  bg: string;
  border: string;
} {
  if (score >= 80) {
    return {
      bar: "bg-green-500",
      text: "text-green-700",
      bg: "bg-green-50",
      border: "border-green-200",
    };
  }
  if (score >= 50) {
    return {
      bar: "bg-amber-500",
      text: "text-amber-700",
      bg: "bg-amber-50",
      border: "border-amber-200",
    };
  }
  return {
    bar: "bg-red-500",
    text: "text-red-700",
    bg: "bg-red-50",
    border: "border-red-200",
  };
}

function TemplateAccuracyBar({
  templateCheck,
}: {
  templateCheck: TemplateCheckSection | null;
}) {
  if (!templateCheck) return null;

  const score = templateCheck.accuracy_score;
  const colors = templateScoreColor(score);

  return (
    <div
      className={`px-4 py-3 border-b border-[#E5E7EB] ${colors.bg} flex-shrink-0`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <LayoutTemplate size={14} className={colors.text} />
          <span className="text-xs font-semibold text-[#374151]">
            Template Accuracy
          </span>
        </div>
        <span className={`text-sm font-bold ${colors.text}`}>
          {score.toFixed(1)}%
        </span>
      </div>
      <div className="h-2 bg-white/70 rounded-full overflow-hidden border border-white/50">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colors.bar}`}
          style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
        />
      </div>
      <p className="text-[10px] text-[#6B7280] mt-1.5">
        {templateCheck.sections_correct}/{templateCheck.total_required_sections}{" "}
        required sections correct
        {templateCheck.violations.length > 0 &&
          ` · ${templateCheck.violations.length} structural issue${templateCheck.violations.length === 1 ? "" : "s"}`}
      </p>
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
        {
          label: "Total Findings",
          value: total,
          icon: BarChart3,
          color: "text-[#374151]",
          bg: "bg-[#F9FAFB]",
          border: "border-[#E5E7EB]",
        },
        {
          label: "High Severity",
          value: high,
          icon: AlertCircle,
          color: "text-red-600",
          bg: "bg-red-50",
          border: "border-red-100",
        },
        {
          label: "Medium Severity",
          value: med,
          icon: AlertTriangle,
          color: "text-amber-600",
          bg: "bg-amber-50",
          border: "border-amber-100",
        },
        {
          label: "Low Severity",
          value: low,
          icon: Info,
          color: "text-blue-600",
          bg: "bg-blue-50",
          border: "border-blue-100",
        },
      ].map(({ label, value, icon: Icon, color, bg, border }) => (
        <div
          key={label}
          className={`rounded-xl p-3 border ${bg} ${border} flex items-center gap-3`}
        >
          <div
            className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center flex-shrink-0 border ${border}`}
          >
            <Icon size={15} className={color} />
          </div>
          <div>
            <p className={`text-xl font-bold ${color} leading-none mb-0.5`}>
              {value}
            </p>
            <p className="text-xs text-[#9CA3AF] font-medium">{label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Terminology helpers ──────────────────────────────────────────────────────

function glossaryUnavailableMessage(reason?: string | null): string {
  if (reason === "llm_unavailable" || reason === "api_quota_exhausted") {
    return "Terminology check unavailable — local LLM busy or offline, try again shortly.";
  }
  return "Terminology check unavailable — please try again shortly.";
}

function TerminologyFindingCard({ finding }: { finding: GlossaryFinding }) {
  const pct = Math.round(finding.confidence * 100);
  return (
    <div className="bg-white rounded-2xl border border-[#E5E7EB] p-4 hover:shadow-sm transition-shadow">
      <div className="flex items-start justify-between gap-2 mb-2">
        <p className="text-xs font-semibold text-[#111827] font-mono">
          “{finding.text_found}”
        </p>
        <span className="text-[10px] font-medium text-[#6B7280] bg-[#F3F4F6] px-2 py-0.5 rounded-md flex-shrink-0">
          {pct}% conf.
        </span>
      </div>
      <p className="text-xs text-[#6B7280] mb-2 leading-relaxed">
        Use:{" "}
        <span className="font-medium text-[#2563EB]">
          {finding.canonical_term}
        </span>
      </p>
      <p className="text-xs text-[#374151] mb-2">{finding.reason}</p>
      <p className="text-[10px] text-[#9CA3AF] font-mono bg-[#F9FAFB] rounded-lg px-2 py-1.5 border border-[#F3F4F6] leading-relaxed">
        …{finding.context_snippet}…
      </p>
    </div>
  );
}

function TerminologyPanel({
  glossaryCheck,
}: {
  glossaryCheck: GlossaryCheckSection | null;
}) {
  if (!glossaryCheck) {
    return (
      <div className="text-center py-10">
        <p className="text-sm text-[#9CA3AF]">No terminology data.</p>
      </div>
    );
  }

  if (glossaryCheck.status === "unavailable") {
    return (
      <div className="bg-white rounded-2xl border border-[#E5E7EB] p-6 text-center">
        <div className="w-10 h-10 rounded-xl bg-[#F3F4F6] text-[#6B7280] flex items-center justify-center mx-auto mb-3">
          <Languages size={18} />
        </div>
        <p className="text-sm text-[#6B7280] leading-relaxed">
          {glossaryUnavailableMessage(glossaryCheck.reason)}
        </p>
      </div>
    );
  }

  if (glossaryCheck.status === "error") {
    return (
      <div className="bg-white rounded-2xl border border-amber-200 p-6 text-center">
        <p className="text-sm text-amber-800 leading-relaxed">
          Terminology check could not be completed. Other analysis results are
          still valid.
        </p>
      </div>
    );
  }

  if (glossaryCheck.findings.length === 0) {
    return (
      <div className="text-center py-12 px-4 bg-white rounded-2xl border border-green-200">
        <div className="w-12 h-12 rounded-2xl bg-green-50 text-green-600 flex items-center justify-center mx-auto mb-3 border border-green-100">
          <CheckCircle2 size={24} />
        </div>
        <h3 className="text-sm font-semibold text-[#111827] mb-1">
          No Terminology Issues
        </h3>
        <p className="text-xs text-[#6B7280] leading-relaxed">
          Draft text matches the standard bilingual glossary for flagged terms.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {glossaryCheck.findings.map((finding, idx) => (
        <TerminologyFindingCard
          key={`${finding.text_found}-${idx}`}
          finding={finding}
        />
      ))}
    </div>
  );
}


function ProcessingView({
  draftText,
  fileName,
  draftDocumentId,
  onComplete,
  onError,
}: {
  draftText: string;
  fileName: string;
  draftDocumentId: number | null;
  onComplete: (result: DraftAnalysisResponse) => void;
  onError: () => void;
}) {
  const [currentStep, setCurrentStep] = useState(0);
  const [analysisResult, setAnalysisResult] = useState<DraftAnalysisResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [stepDetails, setStepDetails] = useState<Record<string, string>>({});

  const runAnalysis = useCallback(() => {
    setErrorMsg(null);
    setCurrentStep(0);
    setDone(false);
    setAnalysisResult(null);
    setStepDetails({});

    analyzeDraftStream(
      draftText,
      (ev: AnalysisProgressEvent) => {
        setStepDetails((prev) => ({
          ...prev,
          [ev.step]: ev.detail,
        }));
        if (ev.step === "read") setCurrentStep(0);
        else if (ev.step === "extract") setCurrentStep(1);
        else if (ev.step === "corpus" || ev.step === "detect") setCurrentStep(2);
        else if (ev.step === "analyse") setCurrentStep(3);
      },
      { grDocumentId: draftDocumentId ?? undefined }
    )
      .then((result) => {
        setAnalysisResult(result);
        setCurrentStep(PROCESSING_STEPS.length - 1);
        setDone(true);
        onComplete(result);
      })


      .catch((err: ApiError | Error) => {
        setErrorMsg(err.message || "Failed to connect to the analysis API.");
      });
  }, [draftText, draftDocumentId, onComplete]);

  useEffect(() => {
    runAnalysis();
  }, [runAnalysis]);

  if (errorMsg) {
    return (
      <div className="flex-1 flex items-center justify-center bg-[#F8FAFC]">
        <div className="w-full max-w-md bg-white rounded-2xl border border-red-200 shadow-lg p-8 text-center">
          <div className="w-12 h-12 rounded-2xl bg-red-50 text-red-600 flex items-center justify-center mx-auto mb-4 border border-red-100">
            <AlertCircle size={24} />
          </div>
          <h2 className="text-base font-semibold text-[#111827] mb-2">
            Analysis Failed
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
              const isStepDone =
                idx < currentStep || (idx === currentStep && done);
              const isActive = idx === currentStep && !done;
              const stepKeyMap: Record<string, string[]> = {
                read: ["read"],
                extract: ["extract"],
                detect: ["corpus", "detect"],
                analyse: ["analyse"],
                complete: [],
              };
              const mappedKeys = stepKeyMap[step.id] || [];
              let dynamicSub: string | undefined;
              for (const k of mappedKeys) {
                if (stepDetails[k]) {
                  dynamicSub = stepDetails[k];
                }
              }
              const displaySub = dynamicSub || step.sub;

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
                        isStepDone
                          ? "text-[#22C55E]/70"
                          : isActive
                            ? "text-[#6B7280]"
                            : "text-[#E5E7EB]"
                      }`}
                    >
                      {step.sub}
                    </p>
                    <div className="h-1 bg-[#F3F4F6] rounded-full overflow-hidden mt-2">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${
                          isStepDone
                            ? "bg-[#22C55E]"
                            : isActive
                              ? "bg-[#2563EB]"
                              : ""
                        }`}
                        style={{
                          width: isStepDone ? "100%" : isActive ? "55%" : "0%",
                        }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {done && analysisResult && (
            <div className="px-8 pb-8">
              <button
                onClick={() => onComplete(analysisResult)}
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
          Cross-referencing statutory database & Neo4j graph · Powered by
          FastAPI Q&A Reasoning Engine
        </p>
      </div>
    </div>
  );
}

// ─── GR structure rules (homepage) ────────────────────────────────────────────

const ANALYSIS_FEATURES = [
  {
    icon: Shield,
    label: "Conflict Detection",
    desc: "Cross-references draft clauses against 1,840+ statutory provisions and Neo4j citation graphs.",
  },
  {
    icon: LayoutTemplate,
    label: "Template Compliance",
    desc: "Rule-based structure check with accuracy score — flags missing or misordered GR sections.",
  },
  {
    icon: Languages,
    label: "Terminology Check",
    desc: "Bilingual glossary review for non-standard Marathi and English terms in operative text.",
  },
  {
    icon: BarChart3,
    label: "Severity Analysis",
    desc: "Findings ranked High / Medium / Low with confidence metrics and filterable summaries.",
  },
  {
    icon: Eye,
    label: "Clause Highlighting",
    desc: "Click any finding to jump to and highlight the matching passage in the document viewer.",
  },
  {
    icon: CheckCircle2,
    label: "Actionable Guidance",
    desc: "Structured recommendations with affected GR excerpts and corpus comparisons.",
  },
] as const;

function GrStructureRulesSection({ compact = false }: { compact?: boolean }) {
  return (
    <section
      className={compact ? "w-full" : "px-6 pb-8 max-w-3xl mx-auto w-full"}
    >
      <div className="bg-white rounded-xl border border-[#E5E7EB] shadow-sm overflow-hidden h-full">
        <div
          className={`border-b border-[#F3F4F6] bg-[#F9FAFB] ${compact ? "px-3 py-3" : "px-6 py-5"}`}
        >
          <div className="flex items-start gap-2">
            <div
              className={`rounded-lg bg-[#EFF6FF] flex items-center justify-center flex-shrink-0 ${
                compact ? "w-7 h-7" : "w-9 h-9 rounded-xl"
              }`}
            >
              <LayoutTemplate
                size={compact ? 14 : 18}
                className="text-[#2563EB]"
              />
            </div>
            <div className="min-w-0">
              <h2
                className={`font-semibold text-[#111827] ${compact ? "text-xs" : "text-sm"}`}
              >
                GR Structure Rules
              </h2>
              <p
                className={`text-[#6B7280] mt-0.5 leading-relaxed ${
                  compact ? "text-[10px]" : "text-xs"
                }`}
              >
                Required section order for Maharashtra resolutions.
              </p>
            </div>
          </div>
        </div>

        <ol className="divide-y divide-[#F3F4F6]">
          {GR_TEMPLATE_RULES.map((rule) => (
            <li
              key={rule.id}
              className={`flex gap-2.5 ${compact ? "px-3 py-2.5" : "px-6 py-4"}`}
            >
              <span
                className={`rounded-full bg-[#111827] text-white font-bold flex items-center justify-center flex-shrink-0 ${
                  compact ? "w-5 h-5 text-[9px]" : "w-7 h-7 text-xs"
                }`}
              >
                {rule.order}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-1 mb-0.5">
                  <h3
                    className={`font-semibold text-[#111827] ${
                      compact ? "text-[11px]" : "text-sm"
                    }`}
                  >
                    {rule.label}
                  </h3>
                  {!compact && (
                    <span className="text-xs text-[#6B7280] font-mono">
                      {rule.labelMr}
                    </span>
                  )}
                  <span
                    className={`font-semibold rounded ${
                      compact
                        ? "text-[9px] px-1 py-px"
                        : "text-[10px] px-2 py-0.5 rounded-md"
                    } ${
                      rule.required
                        ? "bg-red-50 text-red-700 border border-red-100"
                        : "bg-[#F3F4F6] text-[#6B7280] border border-[#E5E7EB]"
                    }`}
                  >
                    {rule.required ? "Req." : "Opt."}
                  </span>
                </div>
                {compact ? (
                  <p className="text-[10px] text-[#6B7280] leading-snug line-clamp-2">
                    {rule.description}
                  </p>
                ) : (
                  <>
                    <p className="text-xs text-[#6B7280] leading-relaxed mb-2">
                      {rule.description}
                    </p>
                    <ul className="space-y-1">
                      {rule.detectionHints.map((hint) => (
                        <li
                          key={hint}
                          className="text-[11px] text-[#374151] flex items-start gap-1.5"
                        >
                          <span className="text-[#9CA3AF] mt-0.5">·</span>
                          <span>{hint}</span>
                        </li>
                      ))}
                    </ul>
                    {rule.required && (
                      <p className="text-[10px] text-[#9CA3AF] mt-2">
                        Missing: {rule.severityMissing} · Misordered:{" "}
                        {rule.severityMisordered}
                      </p>
                    )}
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>

        <div
          className={`bg-[#F9FAFB] border-t border-[#F3F4F6] ${
            compact ? "px-3 py-2" : "px-6 py-3"
          }`}
        >
          <p
            className={`text-[#6B7280] leading-snug ${
              compact ? "text-[9px]" : "text-[11px]"
            }`}
          >
            {GR_TEMPLATE_SCORING_NOTE}
          </p>
        </div>
      </div>
    </section>
  );
}

function AnalysisFeaturesSection() {
  return (
    <section className="w-full">
      <div className="mb-5">
        <h2 className="text-sm font-semibold text-[#111827] mb-1">
          Analysis Capabilities
        </h2>
        <p className="text-xs text-[#6B7280] leading-relaxed max-w-lg">
          Upload a Government Resolution to run conflict, template, and
          terminology checks in parallel against the statutory database.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {ANALYSIS_FEATURES.map(({ icon: Icon, label, desc }) => (
          <div
            key={label}
            className="bg-white rounded-xl border border-[#E5E7EB] p-4 text-left hover:shadow-md hover:-translate-y-0.5 transition-all duration-200"
          >
            <div className="w-7 h-7 rounded-lg bg-[#EFF6FF] flex items-center justify-center mb-3">
              <Icon size={14} className="text-[#2563EB]" />
            </div>
            <p className="text-xs font-semibold text-[#111827] mb-1">{label}</p>
            <p className="text-[11px] text-[#9CA3AF] leading-relaxed">{desc}</p>
          </div>
        ))}
      </div>
    </section>
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
  const [extractError, setExtractError] = useState<string | null>(null);
  const [extracting, setExtracting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const processFile = useCallback(async (file: File) => {
    setFileName(file.name);
    setExtractError(null);
    setExtracting(true);
    try {
      if (isPdfFile(file)) {
        const text = await extractTextFromPdf(file);
        setFileText(text);
      } else {
        const rawText = await file.text();
        const cleanedText = rawText.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, "").trim();
        if (!cleanedText) {
          throw new Error("File contains unreadable binary text. Try pasting the draft GR text instead.");
        }
        setFileText(cleanedText);
      }
    } catch (err: unknown) {
      setFileText("");
      setExtractError(
        err instanceof Error
          ? err.message
          : "Could not read file. Switch to 'Paste Draft GR Text' mode.",
      );
    } finally {
      setExtracting(false);
    }
  }, []);


  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        processFile(e.dataTransfer.files[0]);
      }
    },
    [processFile],
  );

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const handleAnalyse = () => {
    setExtractError(null);
    if (mode === "paste") {
      const textToUse = pastedText.trim();
      if (!textToUse) {
        setExtractError(
          "Paste draft text or load the Maharashtra sample draft.",
        );
        return;
      }
      onUpload(textToUse, "Pasted_Draft_Resolution.txt");
    } else {
      if (!fileText.trim()) {
        setExtractError(
          "Upload a document with readable text, or switch to paste mode.",
        );
        return;
      }
      onUpload(fileText.trim(), fileName || MAHARASHTRA_SAMPLE_FILENAME);
    }
  };

  return (
    <div className="w-full">
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

      {extractError && (
        <div className="mb-3 px-3 py-2 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
          {extractError}
        </div>
      )}

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
              onClick={() => {
                setPastedText(MAHARASHTRA_SAMPLE_DRAFT);
                setExtractError(null);
              }}
              className="text-xs text-[#2563EB] font-medium hover:underline"
            >
              Load Maharashtra Sample Draft
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
                  {extracting ? (
                    <Loader2
                      size={18}
                      className="text-[#2563EB] animate-spin"
                    />
                  ) : (
                    <FileText size={18} className="text-[#22C55E]" />
                  )}
                </div>
                <div>
                  <p className="text-sm font-semibold text-[#111827]">
                    {fileName}
                  </p>
                  <p className="text-xs text-[#6B7280] mt-0.5">
                    {extracting
                      ? "Extracting text from document…"
                      : fileText.length > 0
                        ? `${fileText.length} characters`
                        : "No text extracted — try paste mode"}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {!extracting && fileText.length > 0 && (
                  <span className="flex items-center gap-1.5 text-xs font-semibold text-[#22C55E]">
                    <CheckCircle2 size={13} /> Loaded
                  </span>
                )}
                <button
                  onClick={handleAnalyse}
                  disabled={extracting || !fileText.trim()}
                  className="px-4 py-2.5 rounded-xl bg-[#2563EB] text-white text-sm font-semibold hover:bg-[#1D4ED8] transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
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

// ─── Main App Content ─────────────────────────────────────────────────────────

function MainAppContent() {

  const { profile } = useUserRole();
  const [selectedSharedGrId, setSelectedSharedGrId] = useState<number | null>(null);
  const [viewingCitedGrRef, setViewingCitedGrRef] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("upload");

  const [draftText, setDraftText] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [conflictResult, setConflictResult] = useState<ConflictFinding | null>(
    null,
  );
  const [conflictErrorReason, setConflictErrorReason] = useState<string | null>(
    null,
  );
  const [glossaryCheck, setGlossaryCheck] =
    useState<GlossaryCheckSection | null>(null);
  const [templateCheck, setTemplateCheck] =
    useState<TemplateCheckSection | null>(null);
  const [draftDocumentId, setDraftDocumentId] = useState<number | null>(null);
  const [draftStatus, setDraftStatus] = useState<DraftStatus>("draft");
  const [draftVersionNumber, setDraftVersionNumber] = useState(1);
  const [editedDraftText, setEditedDraftText] = useState("");
  const [savedDraftText, setSavedDraftText] = useState("");
  const [isDirty, setIsDirty] = useState(false);
  const [isPreviewMode, setIsPreviewMode] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRechecking, setIsRechecking] = useState(false);
  const [lastClauseDiff, setLastClauseDiff] = useState<ClauseDiffResult | null>(null);
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);
  const [reviewPanel, setReviewPanel] = useState<
    "conflicts" | "terminology" | "template"
  >("conflicts");

  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [scrollKey, setScrollKey] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [notifOpen, setNotifOpen] = useState(false);
  const [filterSeverity, setFilterSeverity] = useState<Severity | "all">("all");
  const [bookmarks, setBookmarks] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState<{
    checked: boolean;
    reachable: boolean;
    degraded: boolean;
    msg?: string;
  }>({
    checked: false,
    reachable: true,
    degraded: false,
  });

  // Non-blocking initial health check on app load
  useEffect(() => {
    checkHealth()
      .then((res) => {
        const warnings: string[] = [];
        if (!res.db) warnings.push("Postgres unavailable");
        if (!res.neo4j) {
          warnings.push(
            res.neo4j_error
              ? `Neo4j: ${res.neo4j_error}`
              : "Neo4j graph unavailable",
          );
        }
        if (res.embeddings && !res.embeddings.ok) {
          const emb = res.embeddings;
          warnings.push(
            `Embeddings incomplete (${emb.count}/${emb.total_documents} docs embedded)`,
          );
        }
        if (res.store_sync && !res.store_sync.in_sync) {
          warnings.push(
            (res.store_sync.warnings || []).join(" · ") ||
              "Postgres/Neo4j store sync drift detected",
          );
        }
        setBackendStatus({
          checked: true,
          reachable: true,
          degraded: res.status === "degraded" || warnings.length > 0,
          msg: warnings.length > 0 ? warnings.join(" · ") : undefined,
        });
      })
      .catch(() => {
        setBackendStatus({
          checked: true,
          reachable: false,
          degraded: true,
          msg: "FastAPI backend is unreachable at http://localhost:8000. Ensure uvicorn is running.",
        });
      });
  }, []);

  const showToast = (msg: string) => {
    setToast(msg);
  };

  const handleStartUpload = async (text: string, name: string) => {
    setDraftText(text);
    setEditedDraftText(text);
    setSavedDraftText(text);
    setFileName(name);
    setIsDirty(false);
    setDraftDocumentId(null);
    setDraftStatus("draft");
    setDraftVersionNumber(1);
    setIsPreviewMode(false);
    setPhase("processing");

    try {
      const draft = await createDraft(text, name);
      setDraftDocumentId(draft.id);
      setDraftStatus(draft.status);
      setDraftVersionNumber(draft.version_number);
      setSavedDraftText(draft.full_text);
    } catch (err: unknown) {
      console.warn("Draft persistence warning:", err);
      // Non-fatal fallback: allow local reasoning analysis to proceed
    }
  };


  const applyDeterministicResults = (response: DraftSaveResponse) => {
    setGlossaryCheck(response.glossary_check);
    setTemplateCheck(response.template_check);
    setDraftStatus(response.draft.status);
    setDraftVersionNumber(response.draft.version_number);
    setSavedDraftText(response.draft.full_text);
    setDraftText(response.draft.full_text);
    setEditedDraftText(response.draft.full_text);
    setIsDirty(false);
  };

  const applyRecheckResults = (response: DraftRecheckResponse) => {
    applyDeterministicResults(response);
    if (
      response.conflict_check.status === "ok" &&
      response.conflict_check.result
    ) {
      setConflictResult(response.conflict_check.result);
      setConflictErrorReason(null);
    } else {
      setConflictResult(null);
      setConflictErrorReason(response.conflict_check.reason ?? null);
    }
    // Store clause diff so UI can show which clauses were re-checked vs. unchanged
    if (response.clause_diff) {
      setLastClauseDiff(response.clause_diff);
    }
  };

  const handleEditedDraftChange = (text: string) => {
    setEditedDraftText(text);
    setIsDirty(text !== savedDraftText);
  };

  const handleDownloadTxt = () => {
    const textToDownload = editedDraftText || draftText;
    if (!textToDownload || !textToDownload.trim()) {
      showToast("No content available to download.");
      return;
    }
    const cleanName = (fileName || "government_resolution_draft").replace(/\.[^/.]+$/, "");
    exportTextFile(`${cleanName}.txt`, textToDownload);
    showToast(`Downloaded ${cleanName}.txt`);
  };

  const handleShareWithDept = async () => {
    let docId = draftDocumentId;
    if (!docId && editedDraftText) {
      try {
        const created = await createDraft(editedDraftText, fileName || "government_resolution_draft.txt");
        docId = created.id;
        setDraftDocumentId(docId);
      } catch (err: unknown) {
        showToast("Could not create draft record to share.");
        return;
      }
    }
    if (!docId) {
      showToast("No active draft document to share.");
      return;
    }
    try {
      await shareDraftWithDepartment(docId, profile.name);
      showToast("GR Draft shared with department for employee review & Q&A!");
      setPhase("dept_forum");
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Sharing failed";
      showToast(msg);
    }
  };



  const handleSaveDraft = async () => {
    if (!draftDocumentId) {
      showToast("Draft is still being created — try again in a moment.");
      return;
    }
    setIsSaving(true);
    try {
      const response = await saveDraft(draftDocumentId, editedDraftText);
      applyDeterministicResults(response);
      showToast("Draft saved");
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Save failed";
      showToast(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveAndRecheck = async () => {
    if (!draftDocumentId) {
      showToast("Draft is still being created — try again in a moment.");
      return;
    }
    setIsRechecking(true);
    try {
      const response = await saveAndRecheckDraft(
        draftDocumentId,
        editedDraftText,
      );
      applyRecheckResults(response);
      setReviewPanel("conflicts");
      const diff = response.clause_diff;
      const changedCount = (diff?.added?.length ?? 0) + (diff?.modified?.length ?? 0);
      const unchangedCount = diff?.unchanged?.length ?? 0;
      const diffNote = diff?.has_changes
        ? ` · ${changedCount} clause${changedCount !== 1 ? "s" : ""} re-checked, ${unchangedCount} unchanged`
        : " · No clause changes detected";
      showToast(
        response.draft.status === "ready_for_approval"
          ? `Recheck complete — ready for approval${diffNote}`
          : `Recheck complete — issues remain${diffNote}`,
      );
    } catch (err: unknown) {
      const msg = err instanceof ApiError ? err.message : "Recheck failed";
      showToast(msg);
    } finally {
      setIsRechecking(false);
    }
  };

  const handleProcessingComplete = (analysis: DraftAnalysisResponse) => {
    if (
      analysis.conflict_check.status === "ok" &&
      analysis.conflict_check.result
    ) {
      setConflictResult(analysis.conflict_check.result);
      setConflictErrorReason(null);
    } else {
      setConflictResult(null);
      setConflictErrorReason(analysis.conflict_check.reason ?? null);
    }
    setGlossaryCheck(analysis.glossary_check);
    setTemplateCheck(analysis.template_check);
    setEditedDraftText(draftText);
    setSavedDraftText(draftText);
    setIsDirty(false);
    setReviewPanel("conflicts");
    setPhase("review");
    showToast("Draft analysis complete");
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

  const exportTextFile = (filename: string, content: string) => {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  const safeFileName = (rawName: string, fallback: string) => {
    const slug = rawName.trim() || fallback;
    return slug.replace(/\.[^/.]+$/, "") || fallback;
  };

  const hasIssues =
    !!conflictResult?.conflicting ||
    (templateCheck?.violations?.length ?? 0) > 0 ||
    (glossaryCheck?.findings?.length ?? 0) > 0;

  const canExportDraft =
    phase === "review" && !hasIssues && draftText.trim().length > 0;

  const handleDraftExport = () => {
    if (!canExportDraft) {
      showToast("Draft export is available only when no issues are detected");
      return;
    }

    const fileNameForExport = safeFileName(
      fileName || "draft-export",
      "draft-export",
    );
    exportTextFile(`${fileNameForExport}.txt`, draftText);
    showToast("Draft exported");
  };

  const handleReportExport = () => {
    const lines: string[] = [
      "Government Resolution Review Report",
      `Document: ${fileName || "Untitled draft"}`,
      `Generated: ${new Date().toISOString()}`,
      "",
      `Status: ${hasIssues ? "Issues detected" : "No issues detected"}`,
      "",
    ];

    if (conflictResult?.conflicting) {
      lines.push("Conflict findings:");
      conflictFindings.forEach((finding, index) => {
        lines.push(
          `${index + 1}. [${finding.severity.toUpperCase()}] ${finding.summary}`,
        );
        lines.push(`   Clause / reference: ${finding.clauseNumber}`);
        lines.push(`   Conflict type: ${finding.conflictType || "unknown"}`);
        lines.push(`   Analysis: ${finding.analysis}`);
        lines.push(`   Recommendation: ${finding.recommendation}`);
        if (finding.draftExcerpt) {
          lines.push(`   Draft text: ${finding.draftExcerpt}`);
        }
        if (finding.corpusExcerpt) {
          lines.push(`   Related GR text: ${finding.corpusExcerpt}`);
        }
        if (finding.corpusGrNumber) {
          lines.push(`   Related GR number: ${finding.corpusGrNumber}`);
        }
        lines.push("");
      });
    } else {
      lines.push("Conflict findings: none");
      lines.push("");
    }

    if ((templateCheck?.violations?.length ?? 0) > 0) {
      lines.push("Template issues:");
      templateCheck?.violations.forEach((item, index) => {
        lines.push(
          `${index + 1}. [${item.severity.toUpperCase()}] ${item.section_label}`,
        );
        lines.push(`   Type: ${item.violation_type}`);
        if (item.description) {
          lines.push(`   Details: ${item.description}`);
        }
        if (item.expected_after) {
          lines.push(`   Expected after: ${item.expected_after}`);
        }
        if (item.found_at_line) {
          lines.push(`   Found at line: ${item.found_at_line}`);
        }
        lines.push("");
      });
    } else {
      lines.push("Template issues: none");
      lines.push("");
    }

    if ((glossaryCheck?.findings?.length ?? 0) > 0) {
      lines.push("Glossary issues:");
      glossaryCheck?.findings.forEach((item, index) => {
        lines.push(
          `${index + 1}. ${item.message || item.term || "Glossary issue"}`,
        );
      });
      lines.push("");
    } else {
      lines.push("Glossary issues: none");
      lines.push("");
    }

    exportTextFile(
      `${safeFileName(fileName || "report-export", "report-export")}.txt`,
      lines.join("\n"),
    );
    showToast("Report exported");
  };

  // Derive findings from real ConflictFinding response using adapter
  const conflictFindings: Finding[] = conflictResult
    ? mapConflictFindingToFindings(conflictResult)
    : [];

  const templateFindings: Finding[] =
    mapTemplateFindingsToFindings(templateCheck);

  const findings: Finding[] =
    reviewPanel === "template" ? templateFindings : conflictFindings;

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
      {backendStatus.checked &&
        (!backendStatus.reachable || backendStatus.degraded) && (
          <div className="bg-amber-500 text-white text-xs font-semibold py-1.5 px-4 text-center flex items-center justify-center gap-2 z-50">
            <AlertTriangle size={13} />
            {backendStatus.msg ||
              (backendStatus.reachable
                ? "Backend is degraded — retrieval quality may be reduced"
                : "FastAPI backend unreachable")}
          </div>
        )}

      {/* ── Top Navigation Bar ── */}
      <HeaderBar
        phase={phase}
        onNavigate={(targetPhase) => setPhase(targetPhase)}
        onShareWithDept={handleShareWithDept}
        onDownloadTxt={handleDownloadTxt}
        onNewReview={() => {
          setPhase("upload");
          setSelectedFinding(null);
          setConflictResult(null);
          setConflictErrorReason(null);
          setDraftDocumentId(null);
          setDraftStatus("draft");
          setDraftVersionNumber(1);
          setEditedDraftText("");
          setSavedDraftText("");
          setIsDirty(false);
          setIsPreviewMode(false);
          setFilterSeverity("all");
        }}
        onReportExport={handleReportExport}
        draftDocumentId={draftDocumentId}
      />


      {/* ── Upload Phase ── */}
      {phase === "upload" && (
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-6xl mx-auto px-6 pt-8 pb-12 flex flex-col gap-10">
            <UploadCard onUpload={handleStartUpload} />
            <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,300px)_1fr] gap-8 lg:gap-10 items-start pt-8 border-t border-[#E5E7EB]">
              <GrStructureRulesSection compact />
              <AnalysisFeaturesSection />
            </div>
          </div>
        </div>
      )}

      {/* ── Processing Phase ── */}
      {phase === "processing" && (
        <ProcessingView
          draftText={draftText}
          fileName={fileName}
          draftDocumentId={draftDocumentId}
          onComplete={handleProcessingComplete}
          onError={() => setPhase("upload")}
        />
      )}

      {/* ── Review Phase ── */}
      {phase === "review" && (
        <>
          {conflictResult?.degraded && conflictResult.degradation_reasons && (
            <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-xs px-6 py-2 flex items-start gap-2 flex-shrink-0">
              <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
              <div>
                <span className="font-semibold">
                  Analysis ran in degraded mode —{" "}
                </span>
                {conflictResult.degradation_reasons.join(" · ")}
              </div>
            </div>
          )}
          {/* File breadcrumb */}
          <div className="bg-white border-b border-[#E5E7EB] px-6 py-2.5 flex items-center gap-3 flex-shrink-0">
            <div className="flex items-center gap-2 text-xs text-[#6B7280] flex-wrap">
              <FileText size={12} className="text-[#9CA3AF]" />
              <span className="font-medium text-[#374151] font-mono">
                {fileName}
              </span>
              <span className="text-[#D1D5DB]">·</span>
              <span>{editedDraftText.length} characters</span>
              <span className="text-[#D1D5DB]">·</span>
              <DraftStatusBadge status={draftStatus} />
              <span className="text-[#D1D5DB]">·</span>
              <button
                onClick={() => {
                  if (draftDocumentId) {
                    setIsHistoryModalOpen(true);
                  }
                }}
                disabled={!draftDocumentId}
                title={draftDocumentId ? "View GitHub-style version history" : "Save draft first to view version history"}
                className={`inline-flex items-center gap-1.5 font-semibold text-xs px-2.5 py-0.5 rounded-md transition-all ${
                  draftDocumentId
                    ? "bg-blue-50 text-blue-700 hover:bg-blue-100 cursor-pointer border border-blue-200/80 shadow-xs"
                    : "text-[#374151] opacity-75 cursor-not-allowed"
                }`}
              >
                <History size={12} className={draftDocumentId ? "text-blue-600" : "text-[#6B7280]"} />
                <span>Version {draftVersionNumber} History</span>
              </button>
              {isDirty && (
                <>
                  <span className="text-[#D1D5DB]">·</span>
                  <span className="text-amber-600 font-medium">
                    Unsaved changes
                  </span>
                </>
              )}
              <span className="text-[#D1D5DB]">·</span>
              <button
                onClick={handleDownloadTxt}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200/80 px-2.5 py-0.5 rounded-md transition-all cursor-pointer shadow-xs"
                title="Download resolution draft text as a .txt file"
              >
                <Download size={12} className="text-emerald-600" />
                <span>Download .txt</span>
              </button>
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
                  <Search
                    size={11}
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#6B7280]"
                  />
                  <input
                    placeholder="Find in document…"
                    className="w-full pl-7 pr-3 py-1 text-xs bg-white/8 rounded-lg text-[#E5E7EB] placeholder-[#6B7280] border border-white/10 focus:outline-none focus:ring-1 focus:ring-white/25"
                  />
                </div>

                <div className="ml-auto flex items-center gap-2">
                  <button
                    onClick={() => setIsPreviewMode((v) => !v)}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors ${
                      isPreviewMode
                        ? "bg-white/15 text-white"
                        : "text-[#C4C9D4] hover:bg-white/10 hover:text-white"
                    }`}
                    title={isPreviewMode ? "Switch to edit mode" : "Preview with highlights"}
                  >
                    {isPreviewMode ? (
                      <>
                        <Pencil size={12} />
                        Edit
                      </>
                    ) : (
                      <>
                        <Eye size={12} />
                        Preview
                      </>
                    )}
                  </button>

                  <button
                    onClick={handleSaveDraft}
                    disabled={isSaving || isRechecking || !draftDocumentId}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-white/10 text-white hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {isSaving ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <Save size={12} />
                    )}
                    Save Draft
                  </button>

                  <button
                    onClick={handleSaveAndRecheck}
                    disabled={isSaving || isRechecking || !draftDocumentId}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-[#2563EB] text-white hover:bg-[#1D4ED8] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    title="Saves your edits, then runs full conflict recheck"
                  >
                    {isRechecking ? (
                      <Loader2 size={12} className="animate-spin" />
                    ) : (
                      <RefreshCw size={12} />
                    )}
                    Save & Recheck
                  </button>

                  <button
                    onClick={handleDownloadTxt}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-500 transition-colors shadow-xs"
                    title="Download current draft text as a .txt file"
                  >
                    <Download size={12} />
                    Download .txt
                  </button>

                  <button
                    onClick={handleShareWithDept}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-bold bg-[#2563EB] text-white hover:bg-[#1D4ED8] transition-colors shadow-sm"
                    title="Share this draft with the department forum for employee review & Q&A"
                  >
                    <Share2 size={12} />
                    Send to Forum
                  </button>


                  {selectedFinding ? (
                    <span className="flex items-center gap-1.5 text-xs font-medium text-amber-400 ml-1">
                      <AlertTriangle size={12} />
                      Highlighting {selectedFinding.clauseNumber}
                    </span>
                  ) : (
                    <span className="text-xs text-[#6B7280] ml-1">
                      Select a finding to inspect
                    </span>
                  )}
                </div>
              </div>

              <DraftEditor
                value={editedDraftText}
                onChange={handleEditedDraftChange}
                isPreview={isPreviewMode}
                draftText={editedDraftText}
                highlightedFinding={
                  selectedFinding
                    ? {
                        id: selectedFinding.id,
                        matchedText:
                          selectedFinding.matched_text ||
                          selectedFinding.matchedText ||
                          selectedFinding.summary,
                        matched_text:
                          selectedFinding.matched_text ||
                          selectedFinding.matchedText ||
                          selectedFinding.summary,
                        severity: selectedFinding.severity,
                        location: `Pg ${selectedFinding.page}`,
                      }
                    : null
                }
                zoom={zoom}
                scrollTarget={selectedFinding?.id}
                scrollKey={scrollKey}
              />
            </div>

            {/* Findings panel — 35% */}
            <div
              className="flex flex-col border-l border-[#E5E7EB] bg-[#F8FAFC] overflow-hidden"
              style={{ width: "35%" }}
            >
              {/* Summary stats */}
              <SummaryBar
                findings={
                  reviewPanel === "template"
                    ? templateFindings
                    : conflictFindings
                }
              />
              <TemplateAccuracyBar templateCheck={templateCheck} />

              {/* Panel header */}
              <div className="px-4 pt-4 pb-3 border-b border-[#E5E7EB] bg-white flex-shrink-0">
                <div className="flex gap-1.5 mb-3 p-1 bg-[#F3F4F6] rounded-xl">
                  <button
                    onClick={() => setReviewPanel("conflicts")}
                    className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-xs font-semibold transition-all ${
                      reviewPanel === "conflicts"
                        ? "bg-white text-[#111827] shadow-sm"
                        : "text-[#6B7280] hover:text-[#374151]"
                    }`}
                  >
                    <Shield size={12} />
                    Conflicts
                  </button>
                  <button
                    onClick={() => setReviewPanel("template")}
                    className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-xs font-semibold transition-all ${
                      reviewPanel === "template"
                        ? "bg-white text-[#111827] shadow-sm"
                        : "text-[#6B7280] hover:text-[#374151]"
                    }`}
                  >
                    <LayoutTemplate size={12} />
                    Template
                    {templateCheck && templateCheck.violations.length > 0 && (
                      <span className="bg-red-100 text-red-700 text-[10px] px-1.5 py-0.5 rounded-md">
                        {templateCheck.violations.length}
                      </span>
                    )}
                  </button>
                  <button
                    onClick={() => setReviewPanel("terminology")}
                    className={`flex-1 flex items-center justify-center gap-1 py-2 rounded-lg text-xs font-semibold transition-all ${
                      reviewPanel === "terminology"
                        ? "bg-white text-[#111827] shadow-sm"
                        : "text-[#6B7280] hover:text-[#374151]"
                    }`}
                  >
                    <Languages size={12} />
                    Terms
                    {glossaryCheck?.status === "ok" &&
                      glossaryCheck.findings.length > 0 && (
                        <span className="bg-amber-100 text-amber-700 text-[10px] px-1.5 py-0.5 rounded-md">
                          {glossaryCheck.findings.length}
                        </span>
                      )}
                  </button>
                </div>

                {reviewPanel === "conflicts" && (
                  <>
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
                          {s === "all"
                            ? "All"
                            : s.charAt(0).toUpperCase() + s.slice(1)}
                        </button>
                      ))}
                    </div>
                  </>
                )}

                {reviewPanel === "template" && (
                  <div className="flex items-center justify-between mb-1">
                    <h2 className="text-sm font-semibold text-[#111827]">
                      Structure Violations
                    </h2>
                    <span className="text-xs text-[#9CA3AF] bg-[#F3F4F6] px-2 py-0.5 rounded-md font-medium">
                      {templateFindings.length} shown
                    </span>
                  </div>
                )}

                {reviewPanel === "terminology" && (
                  <div className="flex items-center justify-between mb-1">
                    <h2 className="text-sm font-semibold text-[#111827]">
                      Terminology Check
                    </h2>
                    {glossaryCheck?.status === "ok" && (
                      <span className="text-xs text-[#9CA3AF] bg-[#F3F4F6] px-2 py-0.5 rounded-md font-medium">
                        {glossaryCheck.findings.length} flagged
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Findings list */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {reviewPanel === "terminology" ? (
                  <TerminologyPanel glossaryCheck={glossaryCheck} />
                ) : reviewPanel === "template" ? (
                  templateFindings.length === 0 ? (
                    <div className="text-center py-12 px-4 bg-white rounded-2xl border border-green-200">
                      <div className="w-12 h-12 rounded-2xl bg-green-50 text-green-600 flex items-center justify-center mx-auto mb-3 border border-green-100">
                        <CheckCircle2 size={24} />
                      </div>
                      <h3 className="text-sm font-semibold text-[#111827] mb-1">
                        Template Structure OK
                      </h3>
                      <p className="text-xs text-[#6B7280] leading-relaxed">
                        All required GR sections are present and in the expected
                        order.
                      </p>
                    </div>
                  ) : (
                    templateFindings.map((finding) => (
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
                  )
                ) : !conflictResult ? (
                  <div className="bg-white rounded-2xl border border-red-200 p-6 text-center">
                    <p className="text-sm text-red-700 leading-relaxed">
                      Conflict detection could not be completed. Terminology
                      results may still be available in the Terminology tab.
                    </p>
                    {conflictErrorReason && (
                      <p className="mt-2 text-xs text-red-600/90 leading-relaxed">
                        {conflictErrorReason}
                      </p>
                    )}
                  </div>
                ) : conflictResult && !conflictResult.conflicting ? (
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

                {conflictResult?.conflicting &&
                  filteredFindings.length === 0 && (
                    <div className="text-center py-10">
                      <p className="text-sm text-[#9CA3AF]">
                        No findings at this severity level.
                      </p>
                    </div>
                  )}
              </div>
            </div>
          </div>
        </>
      )}

      {/* ── Department Forum Phase ── */}
      {phase === "dept_forum" && (
        <DepartmentForumView
          onSelectSharedGR={(grId) => {
            setSelectedSharedGrId(grId);
            setPhase("shared_detail");
          }}
          onGoToEditor={() => setPhase(conflictResult ? "review" : "upload")}
        />
      )}

      {/* ── Read-Only Shared GR Inspection Phase ── */}
      {phase === "shared_detail" && selectedSharedGrId && (
        <SharedGRDetailView
          grId={selectedSharedGrId}
          onBack={() => setPhase("dept_forum")}
          onDownloadedFinal={() => {
            showToast("GR Finalized & Exported! Removed from In-Progress Forum.");
          }}
        />
      )}

      {/* ── Admin: PDF Template Editor Phase ── */}
      {phase === "pdf_template" && (
        <PdfTemplateEditor />
      )}

      {/* Inspector drawer */}
      <InspectorDrawer
        finding={selectedFinding}
        bookmarked={selectedFinding ? bookmarks.has(selectedFinding.id) : false}
        onClose={() => setSelectedFinding(null)}
        onBookmark={() => selectedFinding && toggleBookmark(selectedFinding.id)}
        onJump={handleJumpToClause}
        onFlag={() => showToast("Finding flagged for legal review")}
        onOpenCitedGR={(grRef) => setViewingCitedGrRef(grRef)}
      />

      {/* Original Cited GR Full-Text Reader Modal */}
      <OriginalGRViewerModal
        grRef={viewingCitedGrRef}
        onClose={() => setViewingCitedGrRef(null)}
      />

      {/* Notif backdrop */}
      {notifOpen && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setNotifOpen(false)}
        />
      )}

      {/* Toast */}
      {toast && <Toast message={toast} onDone={() => setToast(null)} />}

      {draftDocumentId && (
        <VersionHistoryModal
          draftId={draftDocumentId}
          isOpen={isHistoryModalOpen}
          onClose={() => setIsHistoryModalOpen(false)}
          onSelectVersionText={(text, verNum) => {
            setEditedDraftText(text);
            setIsHistoryModalOpen(false);
            showToast(`Loaded content from Version ${verNum}`);
          }}
        />
      )}

      <DraftChatWidget
        draftText={phase === "review" ? editedDraftText : draftText}
        documentKey={`${fileName}::${phase === "review" ? editedDraftText.length : draftText.length}::${(phase === "review" ? editedDraftText : draftText).slice(0, 128)}`}
      />
    </div>
  );
}

export default function App() {
  return (
    <RoleProvider>
      <MainAppContent />
    </RoleProvider>
  );
}

