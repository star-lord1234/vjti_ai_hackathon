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
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

type Severity = "high" | "medium" | "low";
type Phase = "upload" | "processing" | "review";

interface Finding {
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

// ─── Mock Data ────────────────────────────────────────────────────────────────

const FINDINGS: Finding[] = [
  {
    id: "f1",
    severity: "high",
    clauseNumber: "Section 4.2(b)",
    summary: "Ambiguous jurisdiction clause conflicts with Federal Act §12",
    analysis:
      "The jurisdiction clause in Section 4.2(b) grants the State Authority exclusive jurisdiction over environmental impact assessments without adequately accounting for Federal Environment Protection Act §12, which reserves concurrent jurisdiction to the Central Government. This creates a legal conflict that could render enforcement actions unenforceable in appellate proceedings. Previous Supreme Court rulings (2019, AIR 1847) have struck down similar state-level exclusivity provisions.",
    recommendation:
      "Amend Section 4.2(b) to include the phrase \"subject to the provisions of the Federal Environment Protection Act, 2006\" and specify a dispute resolution mechanism for concurrent jurisdiction scenarios. Legal review by the Ministry of Law & Justice is strongly advised before tabling.",
    page: 3,
    lineRange: [142, 158],
    category: "Jurisdiction",
  },
  {
    id: "f2",
    severity: "high",
    clauseNumber: "Section 7.1",
    summary: "Procurement limit exceeds delegated financial authority by 340%",
    analysis:
      "Section 7.1 authorises departmental procurement up to ₹85 crore without Parliamentary approval. The General Financial Rules (GFR) 2017, Rule 147, caps delegated authority at ₹25 crore for this ministry tier. The proposed limit exceeds this by 340%, requiring Parliamentary sanction under Article 112 of the Constitution. Proceeding without this will expose the department to CAG scrutiny and audit objections.",
    recommendation:
      "Reduce the procurement limit in Section 7.1 to ₹25 crore to align with GFR 2017 Rule 147, or initiate a separate Parliamentary appropriation process to raise the delegated threshold before finalising this resolution.",
    page: 5,
    lineRange: [231, 247],
    category: "Financial",
  },
  {
    id: "f3",
    severity: "medium",
    clauseNumber: "Section 9.4",
    summary: "Sunset clause timeline inconsistent with implementation schedule",
    analysis:
      "The sunset clause in Section 9.4 sets automatic expiry at 36 months from notification. However, the implementation schedule detailed in Annexure III projects Phase 3 completion at month 38. This creates a 2-month gap during which the resolution's legal authority lapses while operational activities remain ongoing. Entities relying on delegated powers in Phase 3 will be exposed to legal challenges.",
    recommendation:
      "Extend the sunset clause to 42 months to provide adequate buffer beyond Phase 3 completion, or restructure the Annexure III timeline to complete within 33 months, leaving a 3-month buffer before expiry.",
    page: 7,
    lineRange: [312, 319],
    category: "Timeline",
  },
  {
    id: "f4",
    severity: "medium",
    clauseNumber: "Section 11.2(c)",
    summary: "Data retention requirements conflict with Right to Privacy ruling",
    analysis:
      "Section 11.2(c) mandates indefinite retention of citizen-submitted documents for audit purposes. This is in direct tension with the Supreme Court's landmark 2017 Right to Privacy ruling (K.S. Puttaswamy v. Union of India) which establishes that data retention must be proportionate, necessary, and time-bound. The Personal Data Protection framework further restricts retention beyond the purpose of collection.",
    recommendation:
      "Specify a defined retention period not exceeding 7 years, consistent with standard audit requirements, and include a secure deletion provision. Add a privacy impact assessment clause per Ministry of Electronics & IT guidelines.",
    page: 9,
    lineRange: [389, 402],
    category: "Privacy",
  },
  {
    id: "f5",
    severity: "medium",
    clauseNumber: "Section 14.0",
    summary: "Grievance redressal mechanism lacks mandatory timeline",
    analysis:
      "Section 14.0 establishes a grievance redressal cell but does not prescribe mandatory response timelines for citizen complaints. The Citizens Charter Act requires a maximum 30-day resolution period for government services. Without an explicit timeline, the resolution creates an unenforceable obligation, undermining the accountability mechanism.",
    recommendation:
      "Insert explicit timelines: acknowledgement within 3 working days, interim response within 15 days, and final resolution within 30 days. Include escalation provisions to a Grievance Appellate Authority with a 45-day outer limit.",
    page: 11,
    lineRange: [445, 461],
    category: "Governance",
  },
  {
    id: "f6",
    severity: "low",
    clauseNumber: "Section 2.1",
    summary: "Definition of 'competent authority' is broader than standard usage",
    analysis:
      "The definition of 'competent authority' in Section 2.1 includes District Magistrates and Sub-Divisional Officers, which is broader than the standard definition used in related legislation (Land Acquisition Act, 2013; Forest Rights Act, 2006). This inconsistency may cause interpretive ambiguity when these acts interact with this resolution in field implementation.",
    recommendation:
      "Align the definition with the most recently notified definition under the parent statute, or include a cross-reference note clarifying that the expanded definition applies exclusively to this resolution.",
    page: 1,
    lineRange: [47, 62],
    category: "Definition",
  },
  {
    id: "f7",
    severity: "low",
    clauseNumber: "Section 6.3",
    summary: "Cross-reference to repealed Circular No. 2018/ENV/047",
    analysis:
      "Section 6.3 references Circular No. 2018/ENV/047 for environmental clearance procedures. This circular was superseded by Circular No. 2022/ENV/119 effective from April 2022. Retaining the reference to the repealed circular may cause procedural confusion and could be cited as a drafting defect in future litigation.",
    recommendation:
      "Update the cross-reference in Section 6.3 to Circular No. 2022/ENV/119. Conduct a full cross-reference audit of the document to identify and update any other references to superseded circulars, orders, or rules.",
    page: 5,
    lineRange: [198, 207],
    category: "Reference",
  },
];

const PROCESSING_STEPS = [
  { id: "read", label: "Reading Document", sub: "Parsing PDF structure and metadata", icon: BookOpen },
  { id: "extract", label: "Extracting Clauses", sub: "Identifying 247 numbered clauses", icon: FileText },
  { id: "detect", label: "Detecting Conflicts", sub: "Cross-referencing 1,840 statutory provisions", icon: Shield },
  { id: "analyse", label: "Generating Analysis", sub: "Producing severity assessments", icon: BarChart3 },
  { id: "complete", label: "Review Complete", sub: "7 findings ready for review", icon: CheckCircle2 },
];

// ─── Document paragraphs with finding highlights ──────────────────────────────

interface DocPara {
  id: string;
  type: "header" | "subject" | "section" | "filler";
  label?: string;
  text: string;
  highlight?: string;
  highlightPhrase?: string;
}

const DOCUMENT_PARAGRAPHS: DocPara[] = [
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
    id: "preamble",
    type: "section",
    label: "PREAMBLE",
    text: "WHEREAS, the Government of India recognises the urgent need to establish a coherent, efficient, and legally robust framework for green infrastructure development across the national territory; and\n\nWHEREAS, the existing fragmentation of environmental clearance procedures across multiple ministries and state bodies has led to significant delays in project implementation, causing economic losses estimated at ₹2,340 crore annually; and\n\nWHEREAS, the National Environment Policy, 2006, and subsequent amendments thereto, mandate periodic review and streamlining of environmental governance mechanisms;",
  },
  {
    id: "s1",
    type: "section",
    label: "Section 1 — Short Title and Commencement",
    text: "1.1  This Resolution may be called the National Green Infrastructure Development and Environmental Clearance Streamlining Resolution, 2024.\n\n1.2  It shall come into force on the date of its publication in the Official Gazette.\n\n1.3  Its provisions shall apply to all Union Territories, States having concurrent jurisdiction under Schedule VII, and all Central Government agencies engaged in infrastructure development activities.",
  },
  {
    id: "s2",
    type: "section",
    label: "Section 2 — Definitions",
    highlight: "f6",
    highlightPhrase:
      "any officer not below the rank of District Magistrate, Sub-Divisional Officer (Civil), or equivalent officer of the Central Government",
    text: '2.1  In this Resolution, unless the context otherwise requires —\n\n"Competent Authority" means any officer not below the rank of District Magistrate, Sub-Divisional Officer (Civil), or equivalent officer of the Central Government, authorised by the respective State Government or Union Territory Administration to exercise powers under this Resolution;\n\n"Green Infrastructure" means any network of natural or semi-natural areas, features, and green spaces in rural and urban settings that together maintain or enhance ecological processes;\n\n"Project Proponent" means any person, company, firm, association of persons, or Government department proposing to undertake a project covered under this Resolution.',
  },
  {
    id: "s3",
    type: "section",
    label: "Section 3 — Applicability and Scope",
    text: "3.1  This Resolution shall apply to all green infrastructure projects with a capital outlay exceeding ₹10 crore, whether funded by the Central Government, State Governments, or through public-private partnership arrangements.\n\n3.2  Projects exclusively funded by foreign direct investment shall require prior approval of the Foreign Investment Promotion Board before the provisions of this Resolution are invoked.\n\n3.3  Defence and strategic infrastructure projects are excluded from the purview of this Resolution and shall be governed by the Defence Acquisition Procedure in force.",
  },
  {
    id: "s4",
    type: "section",
    label: "Section 4 — Jurisdiction and Authority",
    highlight: "f1",
    highlightPhrase:
      "EXCLUSIVE JURISDICTION over environmental impact assessments, including the power to commission, review, approve, or reject EIA reports, independent of any Central Government authority",
    text: "4.1  The Ministry of Environment, Forest and Climate Change shall be the nodal Ministry for all matters arising under this Resolution and shall have the power to issue clarifications, amendments, and supplementary guidelines as may be required from time to time.\n\n4.2  State Authorities shall exercise the following powers within their respective territorial jurisdictions:\n\n(a)  Grant of environmental clearance for projects falling within Categories B1 and B2 as notified;\n\n(b)  EXCLUSIVE JURISDICTION over environmental impact assessments, including the power to commission, review, approve, or reject EIA reports, independent of any Central Government authority or agency, in respect of all projects not explicitly listed in Schedule I of this Resolution.",
  },
  {
    id: "s5",
    type: "section",
    label: "Section 5 — Constitution of the National Green Review Committee",
    text: "5.1  The Central Government shall, by notification in the Official Gazette, constitute a National Green Review Committee (hereinafter referred to as the 'Committee') consisting of:\n\n(a)  Secretary, Ministry of Environment, Forest and Climate Change — Chairperson;\n\n(b)  Joint Secretary, Department of Economic Affairs — Member;\n\n(c)  Director General, Forest Survey of India — Member;\n\n(d)  Three independent technical experts nominated by the Chairperson from recognised academic or research institutions.\n\n5.2  The Committee shall meet at least once every quarter and shall submit an annual report to Parliament.",
  },
  {
    id: "s6",
    type: "section",
    label: "Section 6 — Environmental Clearance Procedure",
    highlight: "f7",
    highlightPhrase: "Circular No. 2018/ENV/047",
    text: "6.1  Any Project Proponent seeking environmental clearance shall submit Form EC-1 duly filled and signed to the Competent Authority along with the prescribed fee.\n\n6.2  The Competent Authority shall acknowledge receipt of the application within five working days and assign a unique reference number for tracking purposes.\n\n6.3  The detailed procedure for preparation, submission, and evaluation of Environmental Impact Assessment reports shall be governed by the provisions of Circular No. 2018/ENV/047 issued by this Ministry, as amended from time to time.",
  },
  {
    id: "s7",
    type: "section",
    label: "Section 7 — Financial Powers and Procurement",
    highlight: "f2",
    highlightPhrase:
      "procurement of goods, services, and works up to a value of Rupees Eighty-Five Crore (₹85,00,00,000) without prior Parliamentary sanction",
    text: "7.1  The Competent Authority is hereby delegated the power to approve procurement of goods, services, and works up to a value of Rupees Eighty-Five Crore (₹85,00,00,000) without prior Parliamentary sanction, for projects falling under this Resolution.\n\n7.2  All procurements shall be conducted in accordance with the General Financial Rules, 2017, and the Public Procurement Policy for Micro and Small Enterprises Order, 2012.\n\n7.3  An Internal Audit Committee shall review all procurement decisions exceeding ₹5 crore within thirty days of completion.",
  },
  {
    id: "s8",
    type: "section",
    label: "Section 8 — Public Consultation",
    text: "8.1  For all Category A projects, a mandatory public hearing shall be conducted in the affected area prior to the grant of environmental clearance.\n\n8.2  The public hearing shall be advertised in at least two widely circulated vernacular newspapers in the project area and on the Ministry's official website, not less than thirty days before the scheduled date.\n\n8.3  All objections, representations, and suggestions received during the public consultation period shall be compiled into a Public Response Register and submitted to the Committee.",
  },
  {
    id: "s9",
    type: "section",
    label: "Section 9 — Duration, Review, and Sunset Provisions",
    highlight: "f3",
    highlightPhrase:
      "Resolution shall stand automatically repealed upon the expiry of thirty-six (36) months",
    text: "9.1  This Resolution shall remain in force for the duration specified herein, subject to review by the Committee on an annual basis.\n\n9.2  The Committee shall conduct a comprehensive mid-term review at the end of the eighteenth month and submit its findings to the Minister within sixty days.\n\n9.3  Based on the mid-term review, the Central Government may, by notification, extend, curtail, or modify the provisions of this Resolution.\n\n9.4  Notwithstanding anything contained in the foregoing sub-sections, this Resolution shall stand automatically repealed upon the expiry of thirty-six (36) months from the date of its notification in the Official Gazette, unless earlier extended by a specific order of the Central Government.",
  },
  {
    id: "s10",
    type: "section",
    label: "Section 10 — Monitoring and Compliance",
    text: "10.1  Every Project Proponent shall submit quarterly compliance reports to the Competent Authority in Format MC-7 prescribed in Schedule II.\n\n10.2  The Competent Authority shall maintain a publicly accessible Compliance Dashboard on the Ministry's web portal, updated within seven working days of receipt of compliance reports.\n\n10.3  Non-submission of compliance reports within the stipulated period shall attract a penalty of ₹50,000 per month of default, recoverable as an arrear of land revenue.",
  },
  {
    id: "s11",
    type: "section",
    label: "Section 11 — Data Management and Information Security",
    highlight: "f4",
    highlightPhrase:
      "retained indefinitely in the National Environmental Data Repository for audit and research purposes",
    text: "11.1  The Ministry shall establish and maintain a National Environmental Data Repository (NEDR) for centralised storage of all data, documents, and records generated under this Resolution.\n\n11.2  All records submitted by Project Proponents and Competent Authorities shall be:\n\n(a)  Digitised and uploaded to the NEDR within fifteen working days of receipt;\n\n(b)  Backed up in at least two geographically separate data centres;\n\n(c)  Retained indefinitely in the National Environmental Data Repository for audit and research purposes, regardless of the project status or the expiry of this Resolution.",
  },
  {
    id: "s12",
    type: "section",
    label: "Section 12 — Penalties and Enforcement",
    text: "12.1  Violation of any provision of this Resolution shall be punishable under Section 15 of the Environment (Protection) Act, 1986, in addition to any penalty prescribed under this Resolution.\n\n12.2  The Competent Authority may, after giving a reasonable opportunity of being heard, revoke any environmental clearance granted under this Resolution if the Project Proponent is found to have provided false or misleading information.\n\n12.3  Revocation of environmental clearance shall not absolve the Project Proponent of liability for environmental damage caused during the period of operation.",
  },
  {
    id: "s13",
    type: "section",
    label: "Section 13 — Appellate Authority",
    text: "13.1  Any person aggrieved by an order of the Competent Authority under this Resolution may prefer an appeal to the National Green Tribunal constituted under the National Green Tribunal Act, 2010.\n\n13.2  The appeal shall be filed within thirty days from the date of receipt of the order, along with a fee of ₹10,000.\n\n13.3  The Tribunal shall endeavour to dispose of the appeal within ninety days of filing.",
  },
  {
    id: "s14",
    type: "section",
    label: "Section 14 — Grievance Redressal",
    highlight: "f5",
    highlightPhrase:
      "A Grievance Redressal Cell shall be established in the office of the Competent Authority to receive and address complaints",
    text: "14.1  A Grievance Redressal Cell shall be established in the office of the Competent Authority to receive and address complaints from Project Proponents, affected communities, and other stakeholders.\n\n14.2  The Cell shall be headed by an officer not below the rank of Deputy Secretary and shall have dedicated staff for complaint management.\n\n14.3  All complaints shall be registered in a Grievance Register and acknowledged to the complainant. The Cell shall endeavour to resolve complaints in a reasonable time, taking into account the complexity of each matter.",
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
      {/* Top accent bar */}
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
            {/* Severity colour bar at very top */}
            <div className={`h-1 w-full ${cfg.barBg}`} />

            {/* Header */}
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

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
              {/* Meta grid */}
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

              {/* Jump to clause */}
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

              {/* AI Analysis */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-5 h-5 rounded-md bg-[#EFF6FF] flex items-center justify-center">
                    <BarChart3 size={11} className="text-[#2563EB]" />
                  </div>
                  <h3 className="text-xs font-semibold text-[#6B7280] uppercase tracking-wider">
                    Detailed Analysis
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

              {/* Recommendation */}
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

            {/* Footer */}
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

// ─── DocumentViewer ───────────────────────────────────────────────────────────

function DocumentViewer({
  highlightedFinding,
  zoom,
  scrollTarget,
}: {
  highlightedFinding: string | null;
  zoom: number;
  scrollTarget: string | null;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const paraRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // Scroll to highlighted paragraph when scrollTarget changes
  useEffect(() => {
    if (!scrollTarget || !containerRef.current) return;
    const para = DOCUMENT_PARAGRAPHS.find((p) => p.highlight === scrollTarget);
    if (!para) return;
    const el = paraRefs.current[para.id];
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [scrollTarget]);

  return (
    <div
      ref={containerRef}
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
        {DOCUMENT_PARAGRAPHS.map((para) => {
          const isHighlighted = para.highlight === highlightedFinding;
          return (
            <div
              key={para.id}
              ref={(el) => { paraRefs.current[para.id] = el; }}
              className="mb-7"
            >
              {para.type === "header" && (
                <div className="text-center mb-10 pb-8 border-b-2 border-[#1a1a1a]">
                  {para.text.split("\n").map((line, i) => (
                    <p
                      key={i}
                      className={
                        i < 2
                          ? "font-bold text-base uppercase tracking-widest"
                          : i === 4
                          ? "font-bold text-xl mt-5 mb-1"
                          : "text-sm text-[#374151]"
                      }
                    >
                      {line || <>&nbsp;</>}
                    </p>
                  ))}
                </div>
              )}

              {para.type === "subject" && (
                <div className="mb-8 p-4 border border-[#1a1a1a] bg-[#FAFAFA]">
                  <p className="font-bold text-sm">
                    <span className="underline">Subject:</span>{" "}
                    {para.text.replace("Subject: ", "")}
                  </p>
                </div>
              )}

              {para.type === "section" && (
                <div
                  className={`transition-all duration-400 rounded ${
                    isHighlighted
                      ? "bg-amber-50 border-l-4 border-amber-400 pl-4 -ml-4 py-3"
                      : ""
                  }`}
                >
                  {para.label && (
                    <p
                      className="font-bold mb-3 uppercase tracking-wide"
                      style={{
                        fontFamily: "Inter, sans-serif",
                        fontSize: "11px",
                        letterSpacing: "0.08em",
                      }}
                    >
                      {para.label}
                    </p>
                  )}

                  {isHighlighted && (
                    <div className="flex items-center gap-2 mb-3">
                      <AlertTriangle size={12} className="text-amber-600 flex-shrink-0" />
                      <span
                        className="text-xs font-semibold text-amber-700 bg-amber-100 px-2.5 py-0.5 rounded-md border border-amber-300"
                        style={{ fontFamily: "Inter, sans-serif" }}
                      >
                        Conflict Detected — {FINDINGS.find((f) => f.id === highlightedFinding)?.clauseNumber}
                      </span>
                    </div>
                  )}

                  {para.text.split("\n\n").map((block, i) => {
                    const isConflict =
                      isHighlighted &&
                      para.highlightPhrase &&
                      block.includes(para.highlightPhrase);
                    return (
                      <p key={i} className="mb-3 text-justify">
                        {isConflict && para.highlightPhrase ? (
                          <>
                            {block.split(para.highlightPhrase)[0]}
                            <mark
                              className="rounded px-0.5"
                              style={{
                                background: "rgba(245,158,11,0.25)",
                                borderBottom: "2px solid #F59E0B",
                              }}
                            >
                              {para.highlightPhrase}
                            </mark>
                            {block.split(para.highlightPhrase)[1]}
                          </>
                        ) : (
                          block
                        )}
                      </p>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
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

function ProcessingView({ onComplete }: { onComplete: () => void }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (currentStep < PROCESSING_STEPS.length - 1) {
      const t = setTimeout(() => setCurrentStep((s) => s + 1), 1000);
      return () => clearTimeout(t);
    } else {
      const t = setTimeout(() => setDone(true), 700);
      return () => clearTimeout(t);
    }
  }, [currentStep]);

  return (
    <div className="flex-1 flex items-center justify-center bg-[#F8FAFC]">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl border border-[#E5E7EB] shadow-sm overflow-hidden">
          {/* Card header */}
          <div className="px-8 pt-8 pb-6 border-b border-[#F3F4F6]">
            <div className="flex items-center gap-3 mb-1">
              <div className="w-10 h-10 rounded-xl bg-[#EFF6FF] flex items-center justify-center">
                <Shield size={20} className="text-[#2563EB]" />
              </div>
              <div>
                <h2 className="text-sm font-semibold text-[#111827]">
                  Analysing Resolution
                </h2>
                <p className="text-xs text-[#9CA3AF] mt-0.5">
                  National_Green_Infrastructure_Resolution_2024.pdf
                </p>
              </div>
            </div>
          </div>

          <div className="px-8 py-6 space-y-5">
            {PROCESSING_STEPS.map((step, idx) => {
              const Icon = step.icon;
              const isDone = idx < currentStep;
              const isActive = idx === currentStep;
              return (
                <div key={step.id} className="flex items-start gap-3.5">
                  <div
                    className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5 transition-all duration-500 ${
                      isDone
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
                          isDone
                            ? "text-[#22C55E]"
                            : isActive
                            ? "text-[#111827]"
                            : "text-[#D1D5DB]"
                        }`}
                      >
                        {step.label}
                      </span>
                      {isDone && (
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
                        isDone ? "text-[#22C55E]/70" : isActive ? "text-[#6B7280]" : "text-[#E5E7EB]"
                      }`}
                    >
                      {step.sub}
                    </p>
                    <div className="h-1 bg-[#F3F4F6] rounded-full overflow-hidden mt-2">
                      <div
                        className={`h-full rounded-full transition-all duration-700 ${
                          isDone ? "bg-[#22C55E]" : isActive ? "bg-[#2563EB]" : ""
                        }`}
                        style={{ width: isDone ? "100%" : isActive ? "55%" : "0%" }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {done && (
            <div className="px-8 pb-8">
              <button
                onClick={onComplete}
                className="w-full py-3 rounded-xl bg-[#2563EB] text-white text-sm font-semibold hover:bg-[#1D4ED8] active:bg-[#1E40AF] transition-all duration-200 flex items-center justify-center gap-2 shadow-sm"
              >
                <Eye size={15} />
                View 7 Review Findings
                <ArrowRight size={14} />
              </button>
            </div>
          )}
        </div>

        <p className="text-xs text-[#9CA3AF] text-center mt-4">
          Cross-referencing 1,840 statutory provisions · Powered by automated legal analysis
        </p>
      </div>
    </div>
  );
}

// ─── UploadCard ───────────────────────────────────────────────────────────────

function UploadCard({ onUpload }: { onUpload: () => void }) {
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<string | null>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    setFile("National_Green_Infrastructure_Resolution_2024.pdf");
  }, []);

  const handleBrowse = () => {
    setFile("National_Green_Infrastructure_Resolution_2024.pdf");
  };

  return (
    <div className="px-6 pt-6">
      <div
        className={`rounded-2xl border-2 border-dashed transition-all duration-200 ${
          dragging
            ? "border-[#2563EB] bg-[#EFF6FF] scale-[1.005]"
            : file
            ? "border-[#22C55E] bg-[#F0FDF4]"
            : "border-[#E5E7EB] bg-white hover:border-[#BFDBFE] hover:bg-[#F8FAFC]"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        {file ? (
          <div className="flex items-center justify-between px-6 py-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-[#DCFCE7] flex items-center justify-center">
                <FileText size={18} className="text-[#22C55E]" />
              </div>
              <div>
                <p className="text-sm font-semibold text-[#111827]">{file}</p>
                <p className="text-xs text-[#6B7280] mt-0.5">
                  2.4 MB · PDF Document · 14 pages · Ready to analyse
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5 text-xs font-semibold text-[#22C55E]">
                <CheckCircle2 size={13} /> Uploaded
              </span>
              <button
                onClick={onUpload}
                className="px-4 py-2.5 rounded-xl bg-[#2563EB] text-white text-sm font-semibold hover:bg-[#1D4ED8] transition-colors flex items-center gap-2"
              >
                <Shield size={14} />
                Analyse Document
              </button>
              <button
                onClick={() => setFile(null)}
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
                  onClick={handleBrowse}
                  className="text-[#2563EB] font-semibold hover:underline"
                >
                  browse files
                </button>
                {"  ·  "}PDF, DOCX, DOC — up to 50 MB
              </p>
            </div>
            <button
              onClick={handleBrowse}
              className="px-4 py-2.5 rounded-xl border border-[#E5E7EB] text-sm font-semibold text-[#374151] hover:bg-[#F9FAFB] hover:border-[#D1D5DB] transition-colors flex items-center gap-2 whitespace-nowrap"
            >
              <Upload size={14} />
              Browse File
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [phase, setPhase] = useState<Phase>("upload");
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [scrollTarget, setScrollTarget] = useState<string | null>(null);
  const [zoom, setZoom] = useState(100);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [notifOpen, setNotifOpen] = useState(false);
  const [filterSeverity, setFilterSeverity] = useState<Severity | "all">("all");
  const [bookmarks, setBookmarks] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToast(msg);
  };

  const handleFindingClick = (finding: Finding) => {
    if (selectedFinding?.id === finding.id) {
      setSelectedFinding(null);
    } else {
      setSelectedFinding(finding);
      setScrollTarget(finding.id);
      // Reset scroll target after a tick so repeated clicks still fire
      setTimeout(() => setScrollTarget(null), 100);
    }
  };

  const handleJumpToClause = () => {
    if (!selectedFinding) return;
    setScrollTarget(selectedFinding.id);
    setTimeout(() => setScrollTarget(null), 100);
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

  const filteredFindings =
    filterSeverity === "all"
      ? FINDINGS
      : FINDINGS.filter((f) => f.severity === filterSeverity);

  return (
    <div
      className="h-screen flex flex-col bg-[#F8FAFC] overflow-hidden"
      style={{ fontFamily: "Inter, sans-serif" }}
    >
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
              <span className="font-semibold text-[#111827]">7</span> findings · reviewed{" "}
              <span className="font-semibold text-[#111827]">18 Jul 2024</span>
            </span>
          </div>
        )}

        <div className="flex items-center gap-2">
          {phase === "review" && (
            <>
              <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#E5E7EB] text-xs font-semibold text-[#374151] hover:bg-[#F9FAFB] transition-colors">
                <Download size={12} />
                Export
              </button>
              <button
                onClick={() => {
                  setPhase("upload");
                  setSelectedFinding(null);
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
                  <span className="text-xs text-[#9CA3AF]">1 unread</span>
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
                            Analysis Complete
                          </p>
                          <p className="text-xs text-[#6B7280] leading-relaxed">
                            7 findings detected — 2 high severity require immediate attention
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

          {/* User */}
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
          <UploadCard onUpload={() => setPhase("processing")} />
          <div className="flex flex-col items-center justify-center min-h-[calc(100%-100px)] text-center px-6 py-10">
            <div className="w-14 h-14 rounded-2xl bg-white border border-[#E5E7EB] shadow-sm flex items-center justify-center mb-5">
              <BookOpen size={26} className="text-[#D1D5DB]" />
            </div>
            <h2 className="text-sm font-semibold text-[#374151] mb-1.5">
              No document uploaded yet
            </h2>
            <p className="text-sm text-[#9CA3AF] max-w-sm leading-relaxed mb-10">
              Upload a Government Resolution document to begin automated conflict detection and legal analysis.
            </p>
            <div className="grid grid-cols-3 gap-4 max-w-xl w-full">
              {[
                { icon: Shield, label: "Conflict Detection", desc: "Identifies jurisdiction, financial, and legal conflicts against 1,840+ statutory provisions" },
                { icon: BarChart3, label: "Severity Analysis", desc: "Findings ranked High / Medium / Low with contextual legal reasoning" },
                { icon: CheckCircle2, label: "Actionable Recommendations", desc: "Specific amendment language and cross-references for each finding" },
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
        <ProcessingView onComplete={() => setPhase("review")} />
      )}

      {/* ── Review Phase ── */}
      {phase === "review" && (
        <>
          {/* File breadcrumb */}
          <div className="bg-white border-b border-[#E5E7EB] px-6 py-2.5 flex items-center gap-3 flex-shrink-0">
            <div className="flex items-center gap-2 text-xs text-[#6B7280]">
              <FileText size={12} className="text-[#9CA3AF]" />
              <span className="font-medium text-[#374151]">
                National_Green_Infrastructure_Resolution_2024.pdf
              </span>
              <span className="text-[#D1D5DB]">·</span>
              <span>14 pages</span>
              <span className="text-[#D1D5DB]">·</span>
              <span>2.4 MB</span>
              <span className="text-[#D1D5DB]">·</span>
              <span className="text-[#22C55E] font-medium flex items-center gap-1">
                <CheckCircle2 size={11} />
                Review complete
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
                    {currentPage} / 14
                  </span>
                  <button
                    onClick={() => setCurrentPage((p) => Math.min(14, p + 1))}
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
                      Select a finding to highlight
                    </span>
                  )}
                </div>
              </div>

              <DocumentViewer
                highlightedFinding={selectedFinding?.id ?? null}
                zoom={zoom}
                scrollTarget={scrollTarget}
              />
            </div>

            {/* Findings panel — 35% */}
            <div
              className="flex flex-col border-l border-[#E5E7EB] bg-[#F8FAFC] overflow-hidden"
              style={{ width: "35%" }}
            >
              {/* Summary stats */}
              <SummaryBar findings={FINDINGS} />

              {/* Panel header */}
              <div className="px-4 pt-4 pb-3 border-b border-[#E5E7EB] bg-white flex-shrink-0">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-sm font-semibold text-[#111827]">
                    Review Findings
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
                {filteredFindings.map((finding) => (
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
                ))}

                {filteredFindings.length === 0 && (
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
