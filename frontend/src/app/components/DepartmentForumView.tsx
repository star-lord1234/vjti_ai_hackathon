import React, { useState, useEffect } from "react";
import {
  Building2,
  Search,
  MessageSquare,
  HelpCircle,
  Clock,
  User,
  FileText,
  Lock,
  ArrowRight,
  Filter,
  CheckCircle2,
  RefreshCw,
  PlusCircle,
  Trash2,
} from "lucide-react";
import { InProgressForumGR, fetchInProgressForumGRs, banishDraftFromForum } from "../../lib/api";
import { useUserRole } from "./RoleContext";

interface DepartmentForumViewProps {
  onSelectSharedGR: (grId: number) => void;
  onGoToEditor: () => void;
}

export const DepartmentForumView: React.FC<DepartmentForumViewProps> = ({
  onSelectSharedGR,
  onGoToEditor,
}) => {
  const { profile } = useUserRole();
  const [forumGRs, setForumGRs] = useState<InProgressForumGR[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedDept, setSelectedDept] = useState("all");

  const loadForumGRs = async () => {
    setLoading(true);
    try {
      const list = await fetchInProgressForumGRs();
      setForumGRs(list || []);
    } catch (err) {
      console.error("Failed to load forum GRs", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadForumGRs();
  }, []);

  const filteredGRs = forumGRs.filter((gr) => {
    const matchesSearch =
      (gr.filename || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
      (gr.gr_number_canonical || "").toLowerCase().includes(searchTerm.toLowerCase()) ||
      (gr.department || "").toLowerCase().includes(searchTerm.toLowerCase());
    const matchesDept = selectedDept === "all" || gr.department === selectedDept;
    return matchesSearch && matchesDept;
  });

  const departments = Array.from(
    new Set(forumGRs.map((g) => g.department).filter(Boolean))
  );

  return (
    <div className="flex-1 flex flex-col bg-gray-50 min-h-0 font-sans">
      {/* Top Banner Header */}
      <div className="bg-gradient-to-r from-blue-900 via-blue-800 to-indigo-900 text-white px-8 py-8 shadow-md">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <span className="bg-blue-500/30 text-blue-200 border border-blue-400/30 text-xs font-semibold px-2.5 py-0.5 rounded-full flex items-center gap-1">
                <Building2 size={12} />
                MAHARASHTRA STATE GOVERNMENT
              </span>
              <span className="bg-amber-500/30 text-amber-200 border border-amber-400/30 text-xs font-semibold px-2.5 py-0.5 rounded-full">
                INTER-DEPARTMENTAL COLLABORATION
              </span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Department Collaboration Forum
            </h1>
            <p className="text-xs text-blue-100 mt-1 max-w-2xl leading-relaxed">
              Inspect active in-progress Government Resolutions (GRs), review policy proposals,
              and post questions before final publication.
            </p>
          </div>

          {profile.canEdit && (
            <button
              onClick={onGoToEditor}
              className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition-all shadow-md flex items-center gap-2 self-start md:self-auto"
            >
              <PlusCircle size={16} />
              Draft New GR & Share
            </button>
          )}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 max-w-7xl w-full mx-auto p-8 flex flex-col min-h-0 overflow-hidden">
        {/* Controls Header: Search & Filter */}
        <div className="flex flex-col md:flex-row items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-3 w-full md:w-auto flex-1">
            <div className="relative flex-1 max-w-md">
              <Search
                size={16}
                className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Search in-progress GRs by title, number, or department..."
                className="w-full pl-10 pr-4 py-2.5 text-xs bg-white border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/30 shadow-xs"
              />
            </div>

            {/* Department Filter */}
            <div className="flex items-center gap-2 bg-white px-3 py-2 border border-gray-200 rounded-xl text-xs">
              <Filter size={14} className="text-gray-400" />
              <select
                value={selectedDept}
                onChange={(e) => setSelectedDept(e.target.value)}
                className="bg-transparent font-medium text-gray-700 focus:outline-none"
              >
                <option value="all">All Departments</option>
                {departments.map((dept) => (
                  <option key={dept} value={dept!}>
                    {dept}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <button
            onClick={loadForumGRs}
            className="p-2.5 bg-white border border-gray-200 hover:bg-gray-50 text-gray-600 rounded-xl transition-colors shadow-xs"
            title="Refresh In-Progress GR Feed"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        {/* GR Feed Grid */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="py-16 text-center text-gray-500">
              <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-xs font-semibold">Fetching In-Progress Department GRs...</p>
            </div>
          ) : filteredGRs.length === 0 ? (
            <div className="bg-white rounded-2xl border border-gray-200 p-12 text-center max-w-md mx-auto my-8">
              <FileText size={40} className="mx-auto mb-3 text-gray-300" />
              <h3 className="text-sm font-bold text-gray-900 mb-1">
                No In-Progress GRs Shared Yet
              </h3>
              <p className="text-xs text-gray-500 mb-6 leading-relaxed">
                When drafting officers click <strong>"Share with Dept"</strong> on an active GR, it
                will appear here for employee Q&A and review.
              </p>
              {profile.canEdit && (
                <button
                  onClick={onGoToEditor}
                  className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-sm"
                >
                  Go to GR Editor
                </button>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 pb-8">
              {filteredGRs.map((gr) => (
                <div
                  key={gr.id}
                  className="bg-white rounded-2xl border border-gray-200 hover:border-blue-300 hover:shadow-md transition-all flex flex-col overflow-hidden group"
                >
                  <div className="p-5 flex-1 flex flex-col">
                    {/* Header Tags */}
                    <div className="flex items-center justify-between gap-2 mb-3">
                      <span className="bg-blue-50 text-blue-700 text-[11px] font-bold px-2 py-0.5 rounded-md border border-blue-100">
                        Version {gr.version_count || 1}
                      </span>

                      {gr.unresolved_comment_count > 0 ? (
                        <span className="inline-flex items-center gap-1 bg-amber-50 text-amber-700 text-[11px] font-semibold px-2 py-0.5 rounded-full border border-amber-200">
                          <HelpCircle size={11} />
                          {gr.unresolved_comment_count} Open Question(s)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 bg-emerald-50 text-emerald-700 text-[11px] font-semibold px-2 py-0.5 rounded-full border border-emerald-200">
                          <CheckCircle2 size={11} />
                          All Questions Answered
                        </span>
                      )}
                    </div>

                    {/* Approval Status Badge */}
                    <div className="mb-3">
                      {gr.is_fully_approved ? (
                        <span className="inline-flex items-center gap-1.5 bg-emerald-600 text-white text-[11px] font-bold px-2.5 py-1 rounded-full">
                          <CheckCircle2 size={11} />
                          ✅ Approved — PDF Ready
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 bg-amber-50 text-amber-700 border border-amber-200 text-[11px] font-semibold px-2.5 py-1 rounded-full">
                          <Clock size={11} />
                          ⏳ Awaiting Approvals
                        </span>
                      )}
                    </div>


                    {/* Title */}
                    <h3 className="text-sm font-bold text-gray-900 mb-2 group-hover:text-blue-600 transition-colors line-clamp-2">
                      {gr.filename}
                    </h3>

                    {/* Department & Author Info */}
                    <div className="space-y-1.5 mt-auto pt-4 border-t border-gray-100 text-xs text-gray-600">
                      <div className="flex items-center gap-1.5 text-gray-500">
                        <Building2 size={13} className="text-gray-400 shrink-0" />
                        <span className="truncate">{gr.department || "General Administration Dept"}</span>
                      </div>

                      <div className="flex items-center gap-1.5 text-gray-500">
                        <User size={13} className="text-gray-400 shrink-0" />
                        <span className="truncate">Shared by: {gr.shared_by_user || "Drafting Officer"}</span>
                      </div>

                      {gr.shared_at && (
                        <div className="flex items-center gap-1.5 text-gray-400 text-[11px]">
                          <Clock size={12} className="shrink-0" />
                          <span>{new Date(gr.shared_at).toLocaleDateString()}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Card Action Footer */}
                  <div className="px-5 py-3 bg-gray-50/80 border-t border-gray-100 flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold text-gray-500 flex items-center gap-1">
                      <MessageSquare size={12} />
                      {gr.comment_count} Items
                    </span>

                    <div className="flex items-center gap-2">
                      {profile.canFinalize && gr.is_fully_approved && (
                        <button
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (confirm(`Banish "${gr.filename}" from the Department Forum Dashboard?`)) {
                              await banishDraftFromForum(gr.id);
                              loadForumGRs();
                            }
                          }}
                          className="px-2.5 py-1.5 bg-red-50 hover:bg-red-600 hover:text-white border border-red-200 text-red-600 text-xs font-bold rounded-lg transition-all flex items-center gap-1 shadow-2xs"
                          title="Banish and remove this approved GR from the Dashboard"
                        >
                          <Trash2 size={12} />
                          Banish 🚫
                        </button>
                      )}

                      <button
                        onClick={() => onSelectSharedGR(gr.id)}
                        className="px-3 py-1.5 bg-white hover:bg-blue-600 hover:text-white border border-gray-200 text-blue-600 text-xs font-bold rounded-lg transition-all flex items-center gap-1 shadow-2xs"
                      >
                        Inspect &amp; Q&amp;A
                        <ArrowRight size={13} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
