"""Load glossary JSON once at module import."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from reasoning.glossary.models import GlossaryEntry

_GLOSSARY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "glossary.json"


def _load_glossary() -> List[GlossaryEntry]:
    raw = json.loads(_GLOSSARY_PATH.read_text(encoding="utf-8"))
    return [GlossaryEntry.model_validate(item) for item in raw]


GLOSSARY_ENTRIES: List[GlossaryEntry] = _load_glossary()


def get_glossary_for_prompt() -> str:
    """Compact glossary block for the LLM user prompt."""
    lines: list[str] = []
    for entry in GLOSSARY_ENTRIES:
        canonical_parts: list[str] = []
        if entry.canonical_en:
            canonical_parts.append(entry.canonical_en)
        if entry.canonical_mr:
            canonical_parts.append(entry.canonical_mr)
        canonical = " / ".join(canonical_parts) or entry.id
        variants = ", ".join(entry.variants) if entry.variants else "(none)"
        note = f" [{entry.context_note}]" if entry.context_note else ""
        lines.append(f"- {entry.id}: canonical={canonical}; variants={variants}{note}")
    return "\n".join(lines)
