"""Rule-based GR template / structure compliance checker (no LLM)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from reasoning.findings import AnalysisFinding

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "gr_template_structure.json"


class TemplateSectionConfig(BaseModel):
    id: str
    label: str
    label_mr: Optional[str] = None
    required: bool = True
    severity_missing: Literal["high", "medium", "low"] = "high"
    severity_misordered: Literal["high", "medium", "low"] = "medium"
    weight: float = 1.0


class TemplateStructureConfig(BaseModel):
    version: int = 1
    description: str = ""
    sections: List[TemplateSectionConfig] = Field(default_factory=list)


class TemplateViolation(BaseModel):
    violation_type: Literal["missing", "misordered"]
    section_id: str
    section_label: str
    severity: Literal["high", "medium", "low"]
    description: str
    expected_after: Optional[str] = None
    found_at_line: Optional[int] = None
    char_offset: Optional[int] = None


class TemplateCheckSection(BaseModel):
    status: Literal["ok"] = "ok"
    accuracy_score: float = Field(..., ge=0.0, le=100.0)
    total_required_sections: int
    sections_correct: int
    sections_present: int
    violations: List[TemplateViolation] = Field(default_factory=list)
    findings: List[AnalysisFinding] = Field(default_factory=list)
    section_positions: dict[str, int] = Field(default_factory=dict)
