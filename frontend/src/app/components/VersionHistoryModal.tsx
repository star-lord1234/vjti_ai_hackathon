import React, { useEffect, useState } from "react";
import {
  History,
  X,
  PlusCircle,
  MinusCircle,
  Clock,
  User,
  FileText,
  GitCommit,
  Loader2,
  ChevronRight,
} from "lucide-react";
import { getDraftVersions, VersionHistoryItem } from "../../lib/api";

interface VersionHistoryModalProps {
  draftId: number;
  isOpen: boolean;
  onClose: () => void;
  onSelectVersionText?: (text: string, versionNumber: number) => void;
}

export const VersionHistoryModal: React.FC<VersionHistoryModalProps> = ({
  draftId,
  isOpen,
  onClose,
  onSelectVersionText,
}) => {
  const [versions, setVersions] = useState<VersionHistoryItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState<VersionHistoryItem | null>(null);
  const [activeTab, setActiveTab] = useState<"diff" | "full">("diff");

  useEffect(() => {
    if (isOpen && draftId) {
      setLoading(true);
      setError(null);
      getDraftVersions(draftId)
        .then((items) => {
          setVersions(items);
          if (items.length > 0) {
            setSelectedVersion(items[0]);
          }
        })
        .catch((err) => {
          console.error("Failed to load version history:", err);
          setError(err.message || "Failed to load version history");
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [isOpen, draftId]);

  if (!isOpen) return null;

  const renderDiffLines = (rawDiff?: string | null) => {
    if (!rawDiff || !rawDiff.trim()) {
      return (
        <div className="p-8 text-center text-slate-500 text-sm italic bg-slate-50 dark:bg-slate-900/50 rounded-lg">
          No changes recorded for this initial version.
        </div>
      );
    }

    const lines = rawDiff.split("\n");
    return (
      <div className="font-mono text-xs leading-relaxed overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-950 text-slate-100 p-4">
        {lines.map((line, idx) => {
          if (line.startsWith("+++") || line.startsWith("---")) {
            return (
              <div key={idx} className="text-slate-400 font-semibold py-0.5 select-none">
                {line}
              </div>
            );
          }
          if (line.startsWith("@@")) {
            return (
              <div key={idx} className="text-sky-400 bg-sky-950/60 font-medium py-1 px-2 my-1 rounded select-none">
                {line}
              </div>
            );
          }
          if (line.startsWith("+")) {
            return (
              <div key={idx} className="bg-emerald-950/60 text-emerald-300 px-2 py-0.5 border-l-2 border-emerald-500 my-0.5 flex">
                <span className="text-emerald-500 font-bold mr-2 select-none">+</span>
                <span>{line.substring(1)}</span>
              </div>
            );
          }
          if (line.startsWith("-")) {
            return (
              <div key={idx} className="bg-rose-950/60 text-rose-300 px-2 py-0.5 border-l-2 border-rose-500 my-0.5 flex">
                <span className="text-rose-500 font-bold mr-2 select-none">-</span>
                <span>{line.substring(1)}</span>
              </div>
            );
          }
          return (
            <div key={idx} className="text-slate-300 px-2 py-0.5 flex">
              <span className="text-slate-600 mr-2 select-none">&nbsp;</span>
              <span>{line}</span>
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/80">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 rounded-xl">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                Document Version History
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-medium">
                  Draft #{draftId}
                </span>
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                GitHub-style line & character change tracking (+ / - additions and deletions)
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-200/50 dark:hover:bg-slate-800 rounded-xl transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Panel: Versions List */}
          <div className="w-80 border-r border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 overflow-y-auto p-3 space-y-2">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider px-3 py-1 flex items-center justify-between">
              <span>Versions ({versions.length})</span>
              <GitCommit className="w-3.5 h-3.5" />
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-12 text-slate-400">
                <Loader2 className="w-6 h-6 animate-spin mr-2" />
                <span className="text-sm">Loading history...</span>
              </div>
            ) : error ? (
              <div className="p-4 text-xs text-rose-500 bg-rose-50 dark:bg-rose-950/40 rounded-xl border border-rose-200 dark:border-rose-900">
                {error}
              </div>
            ) : versions.length === 0 ? (
              <div className="p-4 text-xs text-slate-500 text-center">No versions found</div>
            ) : (
              versions.map((ver) => {
                const isSelected = selectedVersion?.version_number === ver.version_number;
                return (
                  <div
                    key={ver.id}
                    onClick={() => setSelectedVersion(ver)}
                    className={`group relative p-3.5 rounded-xl cursor-pointer transition-all border ${
                      isSelected
                        ? "bg-white dark:bg-slate-800 border-blue-500 dark:border-blue-500 shadow-md ring-1 ring-blue-500/20"
                        : "bg-white/60 dark:bg-slate-900/60 border-slate-200/80 dark:border-slate-800/80 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-white dark:hover:bg-slate-800/80"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="inline-flex items-center gap-1.5 text-xs font-bold px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/80 text-blue-600 dark:text-blue-400 border border-blue-200/60 dark:border-blue-900/60">
                        v{ver.version_number}
                      </span>
                      <span className="text-[11px] text-slate-400 flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {ver.created_at ? new Date(ver.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Just now"}
                      </span>
                    </div>

                    <div className="flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400 mb-2">
                      <User className="w-3 h-3 text-slate-400" />
                      <span className="truncate">{ver.actor}</span>
                    </div>

                    {/* GitHub-style Pill Badges */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="inline-flex items-center text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/50 px-2 py-0.5 rounded-full border border-emerald-200/50 dark:border-emerald-900/50">
                        +{ver.lines_added} lines ({ver.chars_added} ch)
                      </span>
                      {ver.lines_deleted > 0 && (
                        <span className="inline-flex items-center text-[11px] font-semibold text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/50 px-2 py-0.5 rounded-full border border-rose-200/50 dark:border-rose-900/50">
                          -{ver.lines_deleted} lines ({ver.chars_deleted} ch)
                        </span>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Right Panel: Selected Version View */}
          <div className="flex-1 flex flex-col bg-white dark:bg-slate-900 overflow-hidden">
            {selectedVersion ? (
              <>
                {/* Version Toolbar */}
                <div className="px-6 py-3 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/50 flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <span className="text-sm font-bold text-slate-800 dark:text-slate-200">
                      Version {selectedVersion.version_number} Details
                    </span>
                    <div className="flex bg-slate-200 dark:bg-slate-800 p-0.5 rounded-lg text-xs font-medium">
                      <button
                        onClick={() => setActiveTab("diff")}
                        className={`px-3 py-1 rounded-md transition-all ${
                          activeTab === "diff"
                            ? "bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm font-semibold"
                            : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
                        }`}
                      >
                        Diff View
                      </button>
                      <button
                        onClick={() => setActiveTab("full")}
                        className={`px-3 py-1 rounded-md transition-all ${
                          activeTab === "full"
                            ? "bg-white dark:bg-slate-700 text-blue-600 dark:text-blue-400 shadow-sm font-semibold"
                            : "text-slate-600 dark:text-slate-400 hover:text-slate-900"
                        }`}
                      >
                        Full Version Text
                      </button>
                    </div>
                  </div>

                  {onSelectVersionText && (
                    <button
                      onClick={() => onSelectVersionText(selectedVersion.full_text, selectedVersion.version_number)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors"
                    >
                      <FileText className="w-3.5 h-3.5" />
                      Restore Version {selectedVersion.version_number}
                    </button>
                  )}
                </div>

                {/* Main View Area */}
                <div className="flex-1 p-6 overflow-y-auto">
                  {activeTab === "diff" ? (
                    <div>
                      <div className="mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-4 text-xs font-medium text-slate-600 dark:text-slate-400">
                          <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                            <PlusCircle className="w-4 h-4" />
                            +{selectedVersion.lines_added} lines / +{selectedVersion.chars_added} characters
                          </span>
                          <span className="flex items-center gap-1 text-rose-600 dark:text-rose-400">
                            <MinusCircle className="w-4 h-4" />
                            -{selectedVersion.lines_deleted} lines / -{selectedVersion.chars_deleted} characters
                          </span>
                        </div>
                        <span className="text-xs text-slate-400 font-mono">
                          Author: {selectedVersion.actor}
                        </span>
                      </div>
                      {renderDiffLines(selectedVersion.raw_diff)}
                    </div>
                  ) : (
                    <div className="font-mono text-xs whitespace-pre-wrap leading-relaxed p-4 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-200 max-h-[60vh] overflow-y-auto">
                      {selectedVersion.full_text}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-400 text-sm">
                Select a version from the timeline to view changes.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
