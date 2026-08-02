"""Response models for combined draft analysis endpoint."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from reasoning.glossary.models import GlossaryCheckSection
from reasoning.models import ConflictFinding
from reasoning.template.models import TemplateCheckSection


class ConflictCheckSection(BaseModel):
    status: Literal["ok", "error"]
    reason: Optional[str] = None
    result: Optional[ConflictFinding] = None


class DraftAnalysisResponse(BaseModel):
    conflict_check: ConflictCheckSection
    glossary_check: GlossaryCheckSection
    template_check: TemplateCheckSection
