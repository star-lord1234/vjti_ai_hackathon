import React, { useState, useEffect } from "react";
import {
  ArrowLeft,
  Lock,
  Building2,
  Calendar,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Download,
  Shield,
  Clock,
  Trash2,
} from "lucide-react";
import {
  GRComment,
  fetchSharedGRDetail,
  finalizeDraftAndExport,
  banishDraftFromForum,
} from "../../lib/api";
import { CommentThread } from "./CommentThread";
import { useUserRole } from "./RoleContext";

interface SharedGRDetailViewProps {
  grId: number;
  onBack: () => void;
  onDownloadedFinal?: () => void;
}

export const SharedGRDetailView: React.FC<SharedGRDetailViewProps> = ({
  grId,
  onBack,
  onDownloadedFinal,
}) => {
  const { profile } = useUserRole();
  const [doc, setDoc] = useState<any>(null);
  const [comments, setComments] = useState<GRComment[]>([]);
  const [versions, setVersions] = useState<any[]>([]);
  const [approvalNotes, setApprovalNotes] = useState<any[]>([]);
  const [isFullyApproved, setIsFullyApproved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const loadDetail = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await fetchSharedGRDetail(grId);
      setDoc(data.gr_document);
      setComments(data.comments || []);
      setVersions(data.versions || []);
      setApprovalNotes(data.approval_notes || []);
      setIsFullyApproved(data.is_fully_approved ?? false);
    } catch (err: any) {
      setErrorMsg(err?.message || "Could not load shared GR details.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDetail();
  }, [grId]);

  const handleCommentAdded = (newComment: GRComment) => {
    setComments((prev) => [...prev, newComment]);
    // Re-fetch to update approval status
    loadDetail();
  };

  const handleResolutionToggled = (commentId: number, isResolved: boolean) => {
    setComments((prev) =>
      prev.map((c) => (c.id === commentId ? { ...c, is_resolved: isResolved } : c))
    );
  };

  const handleFinalizeAndExport = async () => {
    setExporting(true);
    try {
      const result = await finalizeDraftAndExport(grId);

      if (result.exportType === "pdf" && result.pdfBlob) {
        const url = URL.createObjectURL(result.pdfBlob);
        const link = document.createElement("a");
        link.href = url;
        link.download = result.filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      } else {
        // Plain text fallback
        const text = result.textContent ?? doc?.ocr_text ?? "";
        const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = result.filename || doc?.filename || `GR_${grId}.txt`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }

      if (onDownloadedFinal) onDownloadedFinal();
      // Keep user on the page — do not auto-close on download
    } catch (err: any) {
      alert("Failed to export: " + err?.message);
    } finally {
      setExporting(false);
    }
  };

  const [banishing, setBanishing] = useState(false);

  const handleBanish = async () => {
    if (!confirm("Are you sure you want to banish/remove this GR from the Department Forum Dashboard?")) return;
    setBanishing(true);
    try {
      await banishDraftFromForum(grId);
      if (onDownloadedFinal) onDownloadedFinal();
      onBack();
    } catch (err: any) {
      alert("Failed to banish draft: " + err?.message);
    } finally {
      setBanishing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50 p-8">
        <div className="text-center">
          <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-sm font-medium text-gray-600">Loading Shared GR Document...</p>
        </div>
      </div>
    );
  }

  if (errorMsg || !doc) {
    return (
      <div className="flex-1 p-8 bg-gray-50 flex items-center justify-center">
        <div className="bg-white p-6 rounded-2xl border border-red-200 shadow-sm max-w-md text-center">
          <p className="text-sm font-semibold text-red-600 mb-4">{errorMsg || "GR draft not found"}</p>
          <button
            onClick={onBack}
            className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl text-xs font-semibold"
          >
            Back to Forum
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-gray-50 min-h-0 font-sans">
      {/* Top Header Bar */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shadow-xs">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="p-2 rounded-xl border border-gray-200 hover:bg-gray-50 text-gray-600 transition-colors"
          >
            <ArrowLeft size={16} />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1 bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-0.5 rounded-md text-xs font-bold">
                <Lock size={12} />
                READ-ONLY INSPECTION
              </span>
              <span className="bg-blue-50 text-blue-700 text-xs font-semibold px-2 py-0.5 rounded-md border border-blue-100 font-mono">
                Version {doc.version_number || 1}
              </span>
            </div>
            <h1 className="text-base font-bold text-gray-900 mt-1 flex items-center gap-2">
              {doc.filename}
            </h1>
          </div>
        </div>

        {/* Action Toolbar */}
        <div className="flex items-center gap-3">
          {profile.canFinalize && (
            <>
              <button
                onClick={handleFinalizeAndExport}
                disabled={exporting}
                className={`px-4 py-2 rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 shadow-sm ${
                  isFullyApproved
                    ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                    : "bg-gray-700 hover:bg-gray-800 text-white"
                }`}
                title={
                  isFullyApproved
                    ? "All approvals received — export as signed PDF"
                    : "Approvals pending — will export as plain text"
                }
              >
                <Download size={14} />
                {exporting
                  ? "Exporting..."
                  : isFullyApproved
                  ? "Download PDF 📄"
                  : "Download Draft (.txt)"}
              </button>

              <button
                onClick={handleBanish}
                disabled={banishing}
                className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-xs font-semibold transition-all flex items-center gap-1.5 shadow-sm"
                title="Banish and remove this GR from the Department Forum Dashboard"
              >
                <Trash2 size={14} />
                {banishing ? "Banishing..." : "Banish from Dashboard 🚫"}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Approval Status Bar */}
      <div
        className={`px-6 py-3 border-b flex items-center gap-3 text-xs font-semibold ${
          isFullyApproved
            ? "bg-emerald-50 border-emerald-200 text-emerald-800"
            : "bg-amber-50 border-amber-200 text-amber-800"
        }`}
      >
        {isFullyApproved ? (
          <>
            <CheckCircle2 size={15} className="text-emerald-600" />
            <span>All required approvals received — PDF export ready</span>
            <div className="flex items-center gap-2 ml-2 flex-wrap">
              {approvalNotes.map((a: any, i: number) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full"
                >
                  <Shield size={10} />
                  {a.user_name}
                </span>
              ))}
            </div>
          </>
        ) : (
          <>
            <Clock size={15} className="text-amber-600" />
            <span>Awaiting approver sign-off — will export as .txt until fully approved</span>
            {approvalNotes.length > 0 && (
              <span className="text-amber-700 ml-1">
                ({approvalNotes.length} approval{approvalNotes.length !== 1 ? "s" : ""} so far)
              </span>
            )}
          </>
        )}
      </div>

      {/* Main Dual-Pane Workspace */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6 p-6 overflow-hidden min-h-0">
        {/* Left Column: Read-Only GR Text Document Viewer */}
        <div className="lg:col-span-7 flex flex-col bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden min-h-0">
          <div className="p-4 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileText size={16} className="text-blue-600" />
              <span className="text-xs font-bold text-gray-800">Draft Document Provisions</span>
            </div>
            <span className="text-[11px] text-gray-500 font-mono">
              Shared by: {doc.shared_by_user || "Drafting Officer"}
            </span>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-4 font-mono text-xs text-gray-800 bg-gray-50/30 leading-relaxed select-text">
            {doc.ocr_text ? (
              doc.ocr_text.split("\n").map((line: string, idx: number) => (
                <div key={idx} className="flex gap-4 hover:bg-blue-50/40 p-1 rounded transition-colors">
                  <span className="w-8 text-right text-gray-400 select-none font-mono text-[11px]">
                    {idx + 1}
                  </span>
                  <span className="flex-1 whitespace-pre-wrap">{line || " "}</span>
                </div>
              ))
            ) : (
              <p className="text-gray-400 italic">No text content in document.</p>
            )}
          </div>
        </div>

        {/* Right Column: Q&A & Review Comment Discussion Panel */}
        <div className="lg:col-span-5 flex flex-col min-h-0">
          <CommentThread
            grId={grId}
            comments={comments}
            onCommentAdded={handleCommentAdded}
            onResolutionToggled={handleResolutionToggled}
          />
        </div>
      </div>
    </div>
  );
};
