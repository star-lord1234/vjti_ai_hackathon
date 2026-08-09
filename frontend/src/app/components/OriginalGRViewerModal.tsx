import React, { useState, useEffect } from "react";
import {
  X,
  FileText,
  Building2,
  Calendar,
  Search,
  Copy,
  Check,
  BookOpen,
  Lock,
  ExternalLink,
} from "lucide-react";
import { GRDocumentDetail, lookupGRDocument } from "../../lib/api";

interface OriginalGRViewerModalProps {
  grRef: string | number | null;
  onClose: () => void;
}

export const OriginalGRViewerModal: React.FC<OriginalGRViewerModalProps> = ({
  grRef,
  onClose,
}) => {
  const [doc, setDoc] = useState<GRDocumentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!grRef) {
      setDoc(null);
      return;
    }
    loadDocument();
  }, [grRef]);

  const loadDocument = async () => {
    if (!grRef) return;
    setLoading(true);
    setErrorMsg(null);
    try {
      const data = await lookupGRDocument(grRef);
      setDoc(data);
    } catch (err: any) {
      setErrorMsg(err?.message || `Could not find cited GR '${grRef}'.`);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!doc?.ocr_text) return;
    navigator.clipboard.writeText(doc.ocr_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!grRef) return null;

  const lines = (doc?.ocr_text || "").split("\n");
  const filteredLines = filterText.trim()
    ? lines.map((line, i) => ({ line, num: i + 1 })).filter(({ line }) =>
        line.toLowerCase().includes(filterText.toLowerCase())
      )
    : lines.map((line, i) => ({ line, num: i + 1 }));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-xs font-sans">
      <div className="bg-white rounded-2xl border border-gray-200 shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">

        {/* Modal Header */}
        <div className="bg-slate-900 text-white px-6 py-4 flex items-center justify-between border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/20 border border-amber-400/30 flex items-center justify-center text-amber-400">
              <BookOpen size={18} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold tracking-wider uppercase bg-amber-500/20 text-amber-300 border border-amber-400/30 px-2 py-0.5 rounded-full">
                  Original Cited GR
                </span>
                <span className="text-xs text-slate-400 font-mono">
                  {doc?.gr_number_canonical || (typeof grRef === "string" ? grRef : `ID: ${grRef}`)}
                </span>
              </div>
              <h2 className="text-sm font-bold text-white mt-0.5 line-clamp-1">
                {doc?.subject_mr || doc?.filename || "Official Government Resolution"}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {doc?.ocr_text && (
              <button
                onClick={handleCopy}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors border border-slate-700"
                title="Copy full GR text"
              >
                {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                {copied ? "Copied" : "Copy Text"}
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Content Area */}
        {loading ? (
          <div className="flex-1 p-16 text-center bg-gray-50 flex flex-col items-center justify-center">
            <div className="w-10 h-10 border-4 border-amber-600 border-t-transparent rounded-full animate-spin mb-4" />
            <p className="text-sm font-medium text-gray-600">
              Retrieving original GR text from database...
            </p>
          </div>
        ) : errorMsg || !doc ? (
          <div className="flex-1 p-12 bg-gray-50 flex items-center justify-center">
            <div className="bg-white p-6 rounded-2xl border border-red-200 shadow-sm max-w-md text-center">
              <p className="text-sm font-semibold text-red-600 mb-3">
                {errorMsg || "Could not load original GR document."}
              </p>
              <p className="text-xs text-gray-500 mb-5">
                Target reference: <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">{String(grRef)}</code>
              </p>
              <button
                onClick={onClose}
                className="px-4 py-2 bg-gray-900 hover:bg-gray-800 text-white rounded-xl text-xs font-semibold"
              >
                Close Reader
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0 bg-gray-50">
            {/* Metadata Bar */}
            <div className="bg-white px-6 py-3 border-b border-gray-200 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-gray-700">
              <div className="flex items-center gap-1.5">
                <Building2 size={13} className="text-amber-600 shrink-0" />
                <span className="font-semibold">Department:</span>
                <span className="truncate">{doc.department || "General Administration Dept"}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Calendar size={13} className="text-amber-600 shrink-0" />
                <span className="font-semibold">Date:</span>
                <span>{doc.gr_date || "—"}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <FileText size={13} className="text-amber-600 shrink-0" />
                <span className="font-semibold">File:</span>
                <span className="truncate font-mono text-[11px] text-gray-500">{doc.filename}</span>
              </div>
            </div>

            {/* Filter Sub-bar */}
            <div className="bg-slate-100 px-6 py-2 border-b border-slate-200 flex items-center justify-between gap-3">
              <div className="relative flex-1 max-w-xs">
                <Search size={13} className="absolute left-2.5 top-2.5 text-gray-400" />
                <input
                  type="text"
                  value={filterText}
                  onChange={(e) => setFilterText(e.target.value)}
                  placeholder="Search in original GR text..."
                  className="w-full pl-8 pr-3 py-1 text-xs bg-white border border-gray-300 rounded-lg text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-amber-500"
                />
              </div>
              <span className="text-[11px] font-mono text-gray-500">
                {lines.length} total lines {filterText && `(${filteredLines.length} matched)`}
              </span>
            </div>

            {/* Main Full-Text Scroll View */}
            <div className="flex-1 overflow-y-auto p-6 space-y-1 font-mono text-xs text-gray-800 bg-white select-text leading-relaxed">
              {filteredLines.length > 0 ? (
                filteredLines.map(({ line, num }) => (
                  <div key={num} className="flex gap-4 hover:bg-amber-50/50 px-2 py-0.5 rounded transition-colors">
                    <span className="w-10 text-right text-gray-400 select-none font-mono text-[11px] shrink-0">
                      {num}
                    </span>
                    <span className="flex-1 whitespace-pre-wrap font-sans text-xs text-gray-900 leading-normal">
                      {line || " "}
                    </span>
                  </div>
                ))
              ) : (
                <div className="py-12 text-center text-gray-400 italic">
                  No matching text found for "{filterText}".
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
