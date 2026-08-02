"""
Draft document chat endpoint — isolated from analysis reasoning routes.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chat import ChatMessageRequest, ChatMessageResponse, handle_chat_message

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/message", response_model=ChatMessageResponse)
def chat_message(body: ChatMessageRequest) -> ChatMessageResponse:
    """
    Stateless document-aware chat about the current draft.
    Uses GROQ_CHAT_API_KEY only — never the shared analysis key pool.
    """
    return handle_chat_message(body)
