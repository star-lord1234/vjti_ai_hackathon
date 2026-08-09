import React, { useState } from "react";
import {
  MessageSquare,
  HelpCircle,
  CheckCircle2,
  FileCheck,
  Send,
  User,
  Check,
  AlertCircle,
  Tag,
  CornerDownRight,
  Reply,
  ShieldCheck,
} from "lucide-react";
import { GRComment, postGRComment, toggleCommentResolution } from "../../lib/api";
import { useUserRole } from "./RoleContext";

interface CommentThreadProps {
  grId: number;
  comments: GRComment[];
  onCommentAdded: (newComment: GRComment) => void;
  onResolutionToggled: (commentId: number, isResolved: boolean) => void;
}

export const CommentThread: React.FC<CommentThreadProps> = ({
  grId,
  comments,
  onCommentAdded,
  onResolutionToggled,
}) => {
  const { profile } = useUserRole();
  const [filter, setFilter] = useState<string>("all");
  const [commentType, setCommentType] = useState<string>("question");
  const [content, setContent] = useState<string>("");
  const [replyingToId, setReplyingToId] = useState<number | null>(null);
  const [replyContent, setReplyContent] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Group comments into top-level items and nested answers
  const topLevelComments = comments.filter((c) => !c.parent_id);
  const answersByParent = comments.reduce<Record<number, GRComment[]>>((acc, c) => {
    if (c.parent_id) {
      if (!acc[c.parent_id]) acc[c.parent_id] = [];
      acc[c.parent_id].push(c);
    }
    return acc;
  }, {});

  const handlePostTopLevel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!content.trim()) return;
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const newComment = await postGRComment(grId, {
        user_name: profile.name,
        user_role: profile.title,
        user_department: profile.department,
        comment_type: commentType,
        content: content.trim(),
      });
      onCommentAdded(newComment);
      setContent("");
    } catch (err: any) {
      setErrorMsg(err?.message || "Could not post item.");
    } finally {
      setSubmitting(false);
    }
  };

  const handlePostAnswer = async (parentId: number) => {
    if (!replyContent.trim()) return;
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const newAnswer = await postGRComment(grId, {
        parent_id: parentId,
        user_name: profile.name,
        user_role: profile.title,
        user_department: profile.department,
        comment_type: "answer",
        content: replyContent.trim(),
      });
      onCommentAdded(newAnswer);
      setReplyContent("");
      setReplyingToId(null);
    } catch (err: any) {
      setErrorMsg(err?.message || "Could not post answer.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleToggleResolve = async (commentId: number, currentStatus: boolean) => {
    try {
      await toggleCommentResolution(commentId, !currentStatus);
      onResolutionToggled(commentId, !currentStatus);
    } catch (err) {
      console.error("Failed to toggle resolution", err);
    }
  };

  const filteredTopLevel = topLevelComments.filter((c) => {
    if (filter === "all") return true;
    if (filter === "unresolved") return !c.is_resolved;
    if (filter === "questions") return c.comment_type === "question";
    return c.comment_type === filter;
  });

  const getCommentBadge = (type: string, answerCount: number, isResolved: boolean) => {
    switch (type) {
      case "question":
        if (isResolved) {
          return {
            label: "Resolved Question",
            bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
            icon: CheckCircle2,
          };
        }
        if (answerCount > 0) {
          return {
            label: `Answered (${answerCount})`,
            bg: "bg-purple-50 text-purple-700 border-purple-200",
            icon: MessageSquare,
          };
        }
        return {
          label: "Open Question",
          bg: "bg-blue-50 text-blue-700 border-blue-200",
          icon: HelpCircle,
        };
      case "answer":
        return {
          label: "Answer",
          bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
          icon: ShieldCheck,
        };
      case "review_comment":
        return {
          label: "Review Note",
          bg: "bg-purple-50 text-purple-700 border-purple-200",
          icon: MessageSquare,
        };
      case "suggestion":
        return {
          label: "Suggestion",
          bg: "bg-emerald-50 text-emerald-700 border-emerald-200",
          icon: Tag,
        };
      case "approval_note":
        return {
          label: "Approval Note",
          bg: "bg-amber-50 text-amber-700 border-amber-200",
          icon: FileCheck,
        };
      case "system_note":
        return {
          label: "System Event",
          bg: "bg-gray-100 text-gray-600 border-gray-200",
          icon: AlertCircle,
        };
      default:
        return {
          label: "Comment",
          bg: "bg-gray-50 text-gray-700 border-gray-200",
          icon: MessageSquare,
        };
    }
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden font-sans">
      {/* Header Bar */}
      <div className="p-4 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600">
            <HelpCircle size={16} />
          </div>
          <div>
            <h3 className="text-sm font-bold text-gray-900">Department Q&A Forum</h3>
            <p className="text-xs text-gray-500">
              {topLevelComments.length} Questions & Discussions · {comments.length} total entries
            </p>
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex items-center gap-1 bg-white p-1 rounded-lg border border-gray-200 text-xs font-medium">
          <button
            onClick={() => setFilter("all")}
            className={`px-2 py-1 rounded-md transition-colors ${
              filter === "all" ? "bg-blue-600 text-white font-semibold" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilter("questions")}
            className={`px-2 py-1 rounded-md transition-colors ${
              filter === "questions" ? "bg-blue-600 text-white font-semibold" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            Questions
          </button>
          <button
            onClick={() => setFilter("unresolved")}
            className={`px-2 py-1 rounded-md transition-colors ${
              filter === "unresolved" ? "bg-amber-500 text-white font-semibold" : "text-gray-600 hover:bg-gray-100"
            }`}
          >
            Unresolved
          </button>
        </div>
      </div>

      {/* Main Q&A Feed */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 max-h-[520px]">
        {filteredTopLevel.length === 0 ? (
          <div className="py-12 text-center text-gray-400">
            <HelpCircle size={36} className="mx-auto mb-2 text-gray-300" />
            <p className="text-sm font-medium text-gray-600">No questions or discussions yet.</p>
            <p className="text-xs text-gray-400 mt-1">
              Ask a question below to start the department review.
            </p>
          </div>
        ) : (
          filteredTopLevel.map((c) => {
            const answers = answersByParent[c.id] || [];
            const badge = getCommentBadge(c.comment_type, answers.length, c.is_resolved);
            const BadgeIcon = badge.icon;
            const isReplying = replyingToId === c.id;

            return (
              <div
                key={c.id}
                className={`p-4 rounded-xl border transition-all ${
                  c.is_resolved
                    ? "bg-gray-50/70 border-gray-200"
                    : "bg-white border-gray-200 shadow-xs hover:border-blue-300"
                }`}
              >
                {/* Question Header */}
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full bg-blue-100 border border-blue-200 flex items-center justify-center text-blue-700 font-bold text-xs">
                      {c.user_name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-bold text-gray-900">{c.user_name}</span>
                        <span className="text-[10px] text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded font-mono">
                          {c.user_role}
                        </span>
                      </div>
                      <p className="text-[10px] text-gray-400">{c.user_department}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2.5 py-0.5 rounded-full border ${badge.bg}`}
                    >
                      <BadgeIcon size={10} />
                      {badge.label}
                    </span>

                    {/* Resolution toggle button */}
                    {(profile.canEdit || profile.canFinalize) && c.comment_type !== "system_note" && (
                      <button
                        onClick={() => handleToggleResolve(c.id, c.is_resolved)}
                        className={`text-[10px] font-medium px-2 py-0.5 rounded-md border transition-colors flex items-center gap-1 ${
                          c.is_resolved
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : "bg-gray-50 text-gray-600 border-gray-200 hover:bg-emerald-50 hover:text-emerald-700"
                        }`}
                        title={c.is_resolved ? "Mark as unresolved" : "Mark question as resolved"}
                      >
                        <Check size={10} />
                        {c.is_resolved ? "Resolved" : "Resolve"}
                      </button>
                    )}
                  </div>
                </div>

                {/* Question Content */}
                <p className="text-xs text-gray-800 leading-relaxed font-semibold whitespace-pre-wrap pl-10 mb-3">
                  {c.content}
                </p>

                {/* Question Footer Actions */}
                <div className="flex items-center justify-between pl-10 text-[11px] text-gray-500 pt-1 border-t border-gray-100">
                  <span className="font-mono text-[10px] text-gray-400">
                    {c.created_at ? new Date(c.created_at).toLocaleString() : ""}
                  </span>

                  <button
                    onClick={() => {
                      setReplyingToId(isReplying ? null : c.id);
                      setReplyContent("");
                    }}
                    className="text-xs font-bold text-blue-600 hover:text-blue-800 transition-colors flex items-center gap-1"
                  >
                    <Reply size={12} />
                    {isReplying ? "Cancel Reply" : "Reply / Answer Question"}
                  </button>
                </div>

                {/* Answers List (Nested Under Question) */}
                {answers.length > 0 && (
                  <div className="mt-3 pl-6 space-y-2 border-l-2 border-blue-200">
                    {answers.map((ans) => (
                      <div
                        key={ans.id}
                        className="p-3 bg-blue-50/40 rounded-xl border border-blue-100"
                      >
                        <div className="flex items-center justify-between gap-2 mb-1">
                          <div className="flex items-center gap-1.5">
                            <CornerDownRight size={12} className="text-blue-500" />
                            <span className="text-xs font-bold text-gray-900">{ans.user_name}</span>
                            <span className="text-[10px] text-blue-700 bg-blue-100/80 px-1.5 py-0.5 rounded font-mono">
                              {ans.user_role}
                            </span>
                          </div>
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
                            <ShieldCheck size={10} />
                            Answer / Response
                          </span>
                        </div>
                        <p className="text-xs text-gray-800 leading-relaxed font-normal whitespace-pre-wrap pl-4">
                          {ans.content}
                        </p>
                        {ans.created_at && (
                          <div className="text-[10px] text-gray-400 mt-1 pl-4 font-mono">
                            {new Date(ans.created_at).toLocaleString()}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Inline Answer Form Box */}
                {isReplying && (
                  <div className="mt-3 pl-6 border-l-2 border-blue-500 pt-2">
                    <div className="bg-blue-50/60 p-3 rounded-xl border border-blue-200">
                      <p className="text-xs font-bold text-blue-900 mb-1.5 flex items-center gap-1">
                        <Reply size={12} />
                        Answer as {profile.name} ({profile.title}):
                      </p>
                      <textarea
                        value={replyContent}
                        onChange={(e) => setReplyContent(e.target.value)}
                        placeholder="Write your official response or explanation to this question..."
                        rows={2}
                        className="w-full text-xs p-2.5 bg-white border border-blue-200 rounded-lg text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500/30 mb-2"
                      />
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => setReplyingToId(null)}
                          className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-semibold rounded-lg"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => handlePostAnswer(c.id)}
                          disabled={submitting || !replyContent.trim()}
                          className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-lg shadow-2xs disabled:opacity-50 flex items-center gap-1"
                        >
                          <Send size={11} />
                          Submit Answer
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Main Question / Discussion Form */}
      <form onSubmit={handlePostTopLevel} className="p-3 border-t border-gray-100 bg-gray-50/50">
        {errorMsg && <p className="text-xs text-red-600 mb-2 font-medium">{errorMsg}</p>}
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-gray-500 font-medium">Ask Question as:</span>
          <span className="text-xs font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-100">
            {profile.name} ({profile.title})
          </span>
          <select
            value={commentType}
            onChange={(e) => setCommentType(e.target.value)}
            className="ml-auto text-xs border border-gray-200 rounded-lg px-2 py-1 bg-white font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          >
            <option value="question">❓ Ask New Question</option>
            <option value="review_comment">💬 General Review Note</option>
            <option value="suggestion">💡 Policy Suggestion</option>
            {profile.canFinalize && <option value="approval_note">✅ Approval Note</option>}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <input
            type="text"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder={
              commentType === "question"
                ? "Ask a question about this GR draft..."
                : "Type your review comment or suggestion..."
            }
            className="flex-1 text-xs border border-gray-200 rounded-xl px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/30 text-gray-900 placeholder:text-gray-400"
            disabled={submitting}
          />
          <button
            type="submit"
            disabled={submitting || !content.trim()}
            className="px-3.5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold disabled:opacity-50 transition-colors flex items-center gap-1.5 shadow-sm"
          >
            <Send size={12} />
            Post
          </button>
        </div>
      </form>
    </div>
  );
};
