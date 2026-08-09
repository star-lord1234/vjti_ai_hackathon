import React, { useState } from "react";
import {
  Building2,
  FileEdit,
  Share2,
  Download,
  RefreshCw,
  FileText,
  Shield,
  ChevronDown,
  User,
} from "lucide-react";
import maharashtraSeal from "./figma/Seal_of_Maharashtra.svg";
import { useUserRole, ROLE_PROFILES, RoleType } from "./RoleContext";

interface HeaderBarProps {
  phase: string;
  onNavigate: (phase: "upload" | "review" | "dept_forum" | "pdf_template") => void;
  onShareWithDept?: () => void;
  onDownloadTxt?: () => void;
  onNewReview?: () => void;
  onReportExport?: () => void;
  draftDocumentId?: number | null;
}

export const HeaderBar: React.FC<HeaderBarProps> = ({
  phase,
  onNavigate,
  onShareWithDept,
  onDownloadTxt,
  onNewReview,
  onReportExport,
  draftDocumentId,
}) => {
  const { activeRole, profile, switchRole } = useUserRole();
  const [roleOpen, setRoleOpen] = useState(false);

  const isReview = phase === "review";
  const isEditor = phase === "upload" || phase === "processing" || phase === "review";
  const isForum = phase === "dept_forum" || phase === "shared_detail";
  const isTemplate = phase === "pdf_template";

  return (
    <header className="bg-white border-b border-[#E5E7EB] flex-shrink-0 z-30 shadow-sm font-sans">
      {/* Main bar */}
      <div className="flex items-center px-4 h-14 gap-3 min-w-0">

        {/* Brand */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <img
            src={maharashtraSeal}
            alt="Seal of Maharashtra"
            className="w-8 h-8 object-contain"
          />
          <div className="hidden lg:flex flex-col leading-none">
            <span className="text-sm font-bold text-[#111827] tracking-tight">निर्णय सहाय्यता</span>
            <span className="text-[10px] text-[#9CA3AF] font-medium">Maharashtra GR Intelligence</span>
          </div>
        </div>

        {/* Nav Tabs */}
        <div className="flex items-center gap-1 bg-[#F1F5F9] p-1 rounded-xl border border-[#E2E8F0] flex-shrink-0">
          {!profile.canAdmin && (
            <button
              onClick={() => onNavigate(isEditor ? "review" : "upload")}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
                isEditor
                  ? "bg-white text-[#2563EB] shadow-sm"
                  : "text-[#64748B] hover:text-[#0F172A]"
              }`}
            >
              <FileEdit size={13} />
              <span className="hidden sm:inline">GR Editor</span>
            </button>
          )}

          <button
            onClick={() => onNavigate("dept_forum")}
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
              isForum
                ? "bg-[#2563EB] text-white shadow-sm"
                : "text-[#64748B] hover:text-[#0F172A]"
            }`}
          >
            <Building2 size={13} />
            <span className="hidden sm:inline">Dept Forum</span>
          </button>

          {profile.canAdmin && (
            <button
              onClick={() => onNavigate("pdf_template")}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all whitespace-nowrap ${
                isTemplate
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-[#64748B] hover:text-[#0F172A]"
              }`}
            >
              <Shield size={13} />
              <span className="hidden sm:inline">PDF Template</span>
            </button>
          )}
        </div>

        {/* Spacer */}
        <div className="flex-1 min-w-0" />

        {/* Action Toolbar — only on Review phase */}
        {isReview && (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {onShareWithDept && (
              <button
                onClick={onShareWithDept}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-[#2563EB] hover:bg-[#1D4ED8] text-white rounded-lg text-xs font-bold transition-colors shadow-sm whitespace-nowrap"
                title="Share GR draft with department forum for Q&A"
              >
                <Share2 size={13} />
                Send to Forum
              </button>
            )}

            {onDownloadTxt && (
              <button
                onClick={onDownloadTxt}
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-[#E5E7EB] hover:bg-[#F9FAFB] text-[#374151] rounded-lg text-xs font-bold transition-colors whitespace-nowrap"
                title="Download as .txt"
              >
                <Download size={13} />
                <span className="hidden md:inline">Download</span>
              </button>
            )}

            {onReportExport && (
              <button
                onClick={onReportExport}
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-[#E5E7EB] hover:bg-[#F9FAFB] text-[#374151] rounded-lg text-xs font-bold transition-colors whitespace-nowrap"
                title="Export Analysis Report"
              >
                <FileText size={13} />
                <span className="hidden md:inline">Report</span>
              </button>
            )}

            {onNewReview && (
              <button
                onClick={onNewReview}
                className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-[#E5E7EB] hover:bg-[#F9FAFB] text-[#374151] rounded-lg text-xs font-semibold transition-colors whitespace-nowrap"
                title="Start a new GR review"
              >
                <RefreshCw size={13} />
                <span className="hidden lg:inline">New Review</span>
              </button>
            )}
          </div>
        )}

        {/* Role Switcher */}
        <div className="relative flex-shrink-0">
          <div className="flex items-center gap-2 bg-[#F8FAFC] border border-[#E2E8F0] px-2.5 py-1.5 rounded-xl cursor-pointer">
            <div className={`w-6 h-6 rounded-full flex items-center justify-center font-bold text-xs flex-shrink-0 ${
              profile.canAdmin ? "bg-indigo-100 text-indigo-700" :
              profile.canFinalize ? "bg-emerald-100 text-emerald-700" :
              profile.canEdit ? "bg-blue-100 text-blue-700" :
              "bg-gray-100 text-gray-600"
            }`}>
              {profile.name.slice(0, 1)}
            </div>
            <div className="hidden md:block text-left min-w-0">
              <p className="text-xs font-bold text-[#0F172A] leading-none truncate max-w-[100px]">{profile.name.split(" ").slice(0,2).join(" ")}</p>
              <p className="text-[10px] font-medium text-[#64748B] leading-none mt-0.5 truncate max-w-[100px]">{profile.title.split("/")[0].trim()}</p>
            </div>
            <select
              value={activeRole}
              onChange={(e) => switchRole(e.target.value as RoleType)}
              className="absolute inset-0 opacity-0 cursor-pointer w-full"
              title="Switch Role"
            >
              <option value="drafter">Drafting Officer (Edit + Share)</option>
              <option value="reviewer">Employee / Reviewer (Read-Only + Q&A)</option>
              <option value="approver">Joint Secretary / Approver (Read-Only + Finalize)</option>
              <option value="admin">System Administrator (Forum + Template)</option>
            </select>
            <ChevronDown size={12} className="text-[#64748B] flex-shrink-0" />
          </div>
        </div>

      </div>

      {/* Contextual sub-bar for review actions on small screens */}
      {isReview && (
        <div className="md:hidden flex items-center gap-2 px-4 py-2 bg-gray-50 border-t border-gray-100 overflow-x-auto">
          {onShareWithDept && (
            <button
              onClick={onShareWithDept}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#2563EB] text-white rounded-lg text-xs font-bold whitespace-nowrap flex-shrink-0"
            >
              <Share2 size={12} />
              Send to Forum
            </button>
          )}
          {onDownloadTxt && (
            <button
              onClick={onDownloadTxt}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-gray-200 text-gray-700 rounded-lg text-xs font-bold whitespace-nowrap flex-shrink-0"
            >
              <Download size={12} />
              Download
            </button>
          )}
          {onReportExport && (
            <button
              onClick={onReportExport}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-gray-200 text-gray-700 rounded-lg text-xs font-bold whitespace-nowrap flex-shrink-0"
            >
              <FileText size={12} />
              Report
            </button>
          )}
          {onNewReview && (
            <button
              onClick={onNewReview}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-white border border-gray-200 text-gray-700 rounded-lg text-xs font-bold whitespace-nowrap flex-shrink-0"
            >
              <RefreshCw size={12} />
              New Review
            </button>
          )}
        </div>
      )}
    </header>
  );
};
