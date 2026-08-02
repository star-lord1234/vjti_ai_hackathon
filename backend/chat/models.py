"""Pydantic models for the document-aware draft chatbot."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    draft_text: str = ""
    history: List[ChatHistoryMessage] = Field(default_factory=list)
    session_id: str = Field(default="anonymous", max_length=128)


class ChatMessageResponse(BaseModel):
    status: Literal["ok", "unavailable", "no_document", "error"]
    reply: Optional[str] = None
    reason: Optional[str] = None
