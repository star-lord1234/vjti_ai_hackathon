import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, MessageCircle, Send, X } from "lucide-react";
import {
  ChatHistoryMessage,
  ChatMessageResponse,
  sendChatMessage,
} from "../../lib/api";

type LocalMessage =
  | { id: string; kind: "user"; content: string }
  | { id: string; kind: "assistant"; content: string }
  | { id: string; kind: "system"; content: string; variant: "info" | "warning" | "error" };

function newId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function newSessionId(): string {
  return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

interface DraftChatWidgetProps {
  draftText: string;
  documentKey: string;
}

export function DraftChatWidget({ draftText, documentKey }: DraftChatWidgetProps) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const sessionIdRef = useRef(newSessionId());
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevDocumentKeyRef = useRef(documentKey);

  const hasDraft = draftText.trim().length > 0;

  useEffect(() => {
    if (prevDocumentKeyRef.current !== documentKey) {
      prevDocumentKeyRef.current = documentKey;
      sessionIdRef.current = newSessionId();
      setMessages([]);
      setInput("");
    }
  }, [documentKey]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading, open]);

  const appendSystem = useCallback((content: string, variant: LocalMessage["variant"] = "info") => {
    setMessages((prev) => [...prev, { id: newId(), kind: "system", content, variant }]);
  }, []);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    if (!hasDraft) {
      appendSystem(
        "Upload or paste a draft first so I can answer questions about it.",
        "info",
      );
      return;
    }

    const userMsg: LocalMessage = { id: newId(), kind: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    const history: ChatHistoryMessage[] = messages
      .filter((m): m is Extract<LocalMessage, { kind: "user" | "assistant" }> =>
        m.kind === "user" || m.kind === "assistant",
      )
      .map((m) => ({
        role: m.kind,
        content: m.content,
      }));

    let response: ChatMessageResponse;
    try {
      response = await sendChatMessage({
        message: text,
        draftText,
        history,
        sessionId: sessionIdRef.current,
      });
    } catch {
      response = {
        status: "error",
        reason: "network_error",
        reply: "Could not reach the chat service.",
      };
    }

    setLoading(false);

    if (response.status === "ok" && response.reply) {
      setMessages((prev) => [
        ...prev,
        { id: newId(), kind: "assistant", content: response.reply! },
      ]);
      return;
    }

    if (response.status === "unavailable") {
      appendSystem(
        "Chat is temporarily unavailable — API quota exhausted, try again shortly.",
        "warning",
      );
      return;
    }

    if (response.status === "no_document") {
      appendSystem(
        response.reply ||
          "Upload or paste a draft first so I can answer questions about it.",
        "info",
      );
      return;
    }

    appendSystem(
      response.reply || "Something went wrong. Please try again.",
      "error",
    );
  }, [appendSystem, draftText, hasDraft, input, loading, messages]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <>
      {open && (
        <div
          className="fixed bottom-24 right-6 z-[60] w-[min(100vw-2rem,360px)] h-[min(70vh,480px)] flex flex-col bg-white rounded-2xl border border-[#E5E7EB] shadow-2xl overflow-hidden"
          style={{ fontFamily: "Inter, sans-serif" }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-[#E5E7EB] bg-[#F9FAFB] flex-shrink-0">
            <div className="flex items-center gap-2">
              <MessageCircle size={16} className="text-[#2563EB]" />
              <div>
                <p className="text-sm font-semibold text-[#111827]">Draft Assistant</p>
                <p className="text-[10px] text-[#9CA3AF]">Questions about your current draft</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="p-1.5 rounded-lg hover:bg-[#E5E7EB] text-[#6B7280] transition-colors"
              aria-label="Close chat"
            >
              <X size={16} />
            </button>
          </div>

          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3 bg-[#F8FAFC]">
            {messages.length === 0 && !loading && (
              <p className="text-xs text-[#9CA3AF] text-center py-6 leading-relaxed">
                {hasDraft
                  ? "Ask about clauses, structure, or wording in your uploaded draft."
                  : "Upload or paste a draft first so I can answer questions about it."}
              </p>
            )}

            {messages.map((msg) => {
              if (msg.kind === "system") {
                const styles =
                  msg.variant === "warning"
                    ? "bg-amber-50 border-amber-200 text-amber-800"
                    : msg.variant === "error"
                      ? "bg-red-50 border-red-200 text-red-700"
                      : "bg-[#EFF6FF] border-[#BFDBFE] text-[#1E40AF]";
                return (
                  <div
                    key={msg.id}
                    className={`text-xs rounded-xl border px-3 py-2 leading-relaxed ${styles}`}
                  >
                    {msg.content}
                  </div>
                );
              }

              const isUser = msg.kind === "user";
              return (
                <div
                  key={msg.id}
                  className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[85%] text-xs leading-relaxed rounded-2xl px-3 py-2 ${
                      isUser
                        ? "bg-[#2563EB] text-white rounded-br-md"
                        : "bg-white border border-[#E5E7EB] text-[#374151] rounded-bl-md shadow-sm"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              );
            })}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-white border border-[#E5E7EB] rounded-2xl rounded-bl-md px-3 py-2 shadow-sm flex items-center gap-2 text-xs text-[#6B7280]">
                  <Loader2 size={14} className="animate-spin text-[#2563EB]" />
                  Thinking…
                </div>
              </div>
            )}
          </div>

          <div className="p-3 border-t border-[#E5E7EB] bg-white flex-shrink-0">
            <div className="flex gap-2 items-end">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                rows={2}
                placeholder={
                  hasDraft ? "Ask about this draft…" : "Load a draft to start chatting"
                }
                disabled={loading}
                className="flex-1 resize-none text-xs p-2.5 rounded-xl border border-[#E5E7EB] bg-[#F9FAFB] focus:outline-none focus:ring-2 focus:ring-[#2563EB]/20 focus:border-[#2563EB] disabled:opacity-60"
              />
              <button
                type="button"
                onClick={() => void handleSend()}
                disabled={loading || !input.trim()}
                className="p-2.5 rounded-xl bg-[#2563EB] text-white hover:bg-[#1D4ED8] disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex-shrink-0"
                aria-label="Send message"
              >
                <Send size={16} />
              </button>
            </div>
            <p className="text-[9px] text-[#9CA3AF] mt-2 leading-snug">
              Not legal advice — summarizes and explains the draft text only.
            </p>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`fixed bottom-6 right-6 z-[60] w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-200 ${
          open
            ? "bg-[#1E40AF] text-white scale-95"
            : "bg-[#2563EB] text-white hover:bg-[#1D4ED8] hover:scale-105"
        }`}
        aria-label={open ? "Close draft chat" : "Open draft chat"}
      >
        {open ? <X size={22} /> : <MessageCircle size={22} />}
      </button>
    </>
  );
}
