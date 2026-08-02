"""Generic analysis finding shape shared across checkers."""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class AnalysisFinding(BaseModel):
    """Maps to the frontend Finding interface for panel + highlighting."""

    id: str
    severity: Literal["high", "medium", "low"]
    category: str
    summary: str
    matched_text: str = ""
    location: str = ""
    description: str = ""
    analysis: str = ""
    recommendation: str = ""
    line_number: Optional[int] = None
    char_offset: Optional[int] = None
    line_range: List[int] = Field(default_factory=lambda: [0, 0])
