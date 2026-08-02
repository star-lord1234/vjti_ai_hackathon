"""Pydantic models for glossary terminology checking."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class GlossaryEntry(BaseModel):
    id: str
    canonical_en: Optional[str] = None
    canonical_mr: Optional[str] = None
    variants: List[str] = Field(default_factory=list)
    context_note: Optional[str] = None


class GlossaryFinding(BaseModel):
    text_found: str = Field(..., description="Exact non-standard text found in the draft")
    context_snippet: str = Field(
        ...,
        description="Short surrounding snippet showing where the term appears",
    )
    canonical_term: str = Field(
        ...,
        description="Canonical replacement term from the glossary",
    )
    reason: str = Field(..., description="One-line explanation of the inconsistency")
    confidence: float = Field(..., ge=0.0, le=1.0)


class GlossaryLLMOutput(BaseModel):
    findings: List[GlossaryFinding] = Field(default_factory=list)


class GlossaryCheckSection(BaseModel):
    status: Literal["ok", "unavailable", "error"]
    reason: Optional[str] = None
    findings: List[GlossaryFinding] = Field(default_factory=list)
