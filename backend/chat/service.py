"""
Document-aware GR draft chatbot — isolated Groq client (GROQ_CHAT_API_KEY only).

Does NOT use the shared analysis APIManager or reasoning LLM paths.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from groq import Groq

from chat.exceptions import ChatRateLimited, ChatUnavailable
from chat.models import ChatHistoryMessage, ChatMessageRequest, ChatMessageResponse
from chat.rate_limit import check_rate_limit

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger(__name__)

CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "llama-3.1-8b-instant")
CHAT_MAX_TOKENS = int(os.getenv("GROQ_CHAT_MAX_TOKENS", "400"))
CHAT_MAX_DRAFT_CHARS = int(os.getenv("GROQ_CHAT_MAX_DRAFT_CHARS", "8000"))
CHAT_MAX_HISTORY = int(os.getenv("GROQ_CHAT_MAX_HISTORY", "12"))
CHAT_TEMPERATURE = float(os.getenv("GROQ_CHAT_TEMPERATURE", "0.2"))
CHAT_COOLDOWN_SECONDS = float(os.getenv("GROQ_CHAT_COOLDOWN_SECONDS", "30"))

_SYSTEM_PROMPT = """You are a Maharashtra Government Resolution (GR) drafting assistant embedded in a review tool.

You help the user understand the SPECIFIC draft text provided below. Rules:
- Ground document-specific answers ONLY in the draft text supplied. If the draft does not contain enough information, say so clearly — do not guess or invent provisions.
- You may summarize, explain structure, clarify wording, or point to relevant clauses in the draft.
- Do NOT provide legal advice, authoritative interpretations, or recommendations on whether the draft is legally valid.
- Keep replies concise (a few short paragraphs at most). This is a side-panel chat, not a report.
- If asked about conflicts, corpus policy, or statutory compliance beyond the draft text, explain that full analysis runs separately in the app's analysis panels.
"""

_chat_client: Optional[Groq] = None
_chat_cooldown_until: float = 0.0


def _get_chat_client() -> Groq:
    global _chat_client
    if _chat_client is None:
        api_key = os.getenv("GROQ_CHAT_API_KEY", "").strip()
        if not api_key:
            raise ChatUnavailable("chat_api_key_missing")
        _chat_client = Groq(api_key=api_key)
        logger.info("Initialized isolated Groq chat client (GROQ_CHAT_API_KEY).")
    return _chat_client


def _require_chat_available() -> None:
    global _chat_cooldown_until
    if time.time() < _chat_cooldown_until:
        raise ChatUnavailable("api_quota_exhausted")


def _mark_chat_rate_limited(retry_after: Optional[float] = None) -> None:
    global _chat_cooldown_until
    cooldown = float(retry_after) if retry_after is not None else CHAT_COOLDOWN_SECONDS
    cooldown = max(1.0, cooldown) + 0.35
    _chat_cooldown_until = max(_chat_cooldown_until, time.time() + cooldown)
    logger.warning("Chat API key cooling for %.1fs (isolated from analysis pool).", cooldown)


def _trim_draft(draft_text: str) -> str:
    text = draft_text.strip()
    if len(text) <= CHAT_MAX_DRAFT_CHARS:
        return text
    return text[:CHAT_MAX_DRAFT_CHARS] + "\n\n[… draft truncated for chat context …]"


def _build_messages(
    draft_text: str,
    history: List[ChatHistoryMessage],
    user_message: str,
) -> list[dict[str, str]]:
    draft_excerpt = _trim_draft(draft_text)
    system = (
        _SYSTEM_PROMPT
        + "\n\n--- DRAFT TEXT (sole source for document-specific answers) ---\n"
        + draft_excerpt
    )

    messages: list[dict[str, str]] = [{"role": "system", "content": system}]

    recent = history[-CHAT_MAX_HISTORY:] if history else []
    for item in recent:
        messages.append({"role": item.role, "content": item.content})

    messages.append({"role": "user", "content": user_message})
    return messages


def handle_chat_message(request: ChatMessageRequest) -> ChatMessageResponse:
    if not request.draft_text.strip():
        return ChatMessageResponse(
            status="no_document",
            reason="no_draft_loaded",
            reply="Upload or paste a draft first so I can answer questions about it.",
        )

    if not check_rate_limit(request.session_id):
        return ChatMessageResponse(
            status="error",
            reason="rate_limit_exceeded",
            reply="Too many messages — please wait a moment before sending again.",
        )

    try:
        _require_chat_available()
        client = _get_chat_client()
        messages = _build_messages(
            request.draft_text,
            request.history,
            request.message.strip(),
        )

        completion = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=CHAT_TEMPERATURE,
            max_tokens=CHAT_MAX_TOKENS,
        )
        reply = (completion.choices[0].message.content or "").strip()
        if not reply:
            return ChatMessageResponse(
                status="error",
                reason="empty_model_response",
                reply="I couldn't generate a reply. Please try again.",
            )
        return ChatMessageResponse(status="ok", reply=reply)

    except ChatUnavailable as exc:
        logger.warning("Chat unavailable: %s", exc.reason)
        return ChatMessageResponse(status="unavailable", reason=exc.reason)

    except ChatRateLimited as exc:
        return ChatMessageResponse(status="error", reason=exc.reason)

    except Exception as exc:
        err = str(exc).lower()
        if any(kw in err for kw in ("rate limit", "429", "quota", "tokens per")):
            _mark_chat_rate_limited()
            logger.warning("Chat Groq rate limit: %s", exc)
            return ChatMessageResponse(status="unavailable", reason="api_quota_exhausted")

        logger.exception("Chat message failed: %s", exc)
        return ChatMessageResponse(
            status="error",
            reason="chat_request_failed",
            reply="Something went wrong reaching the chat service. Please try again.",
        )
