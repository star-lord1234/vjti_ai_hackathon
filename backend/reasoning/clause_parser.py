"""
Clause-level parsing for draft GR text (operative provisions).
"""

from __future__ import annotations

import re
from typing import List

_SECTION_EN = re.compile(
    r"^\s*(?:Section|SEC\.?)\s*(\d+(?:\.\d+)*)[.\s:\-—–]*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_SECTION_MR = re.compile(
    r"^\s*(?:कलम|धारा)\s*(\d+(?:\.\d+)*)[.\s:\-—–]*(.+)$",
    re.MULTILINE,
)
_NUMBERED = re.compile(
    r"^\s*((?:\d+\.)+\d+|\d+[.)])\s+(.{20,})$",
    re.MULTILINE,
)


def extract_draft_clauses(text: str, max_clauses: int = 12) -> List[str]:
    """
    Extract operative clause/section blocks from draft text for clause-aligned retrieval.
    """
    text = (text or "").strip()
    if not text:
        return []

    clauses: List[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        cleaned = re.sub(r"\s+", " ", raw).strip()
        if len(cleaned) < 25:
            return
        key = cleaned[:80]
        if key in seen:
            return
        seen.add(key)
        clauses.append(cleaned)

    for pattern in (_SECTION_EN, _SECTION_MR, _NUMBERED):
        for match in pattern.finditer(text):
            num, body = match.group(1), match.group(2).strip()
            _add(f"{num} {body}")

    # Line-by-line numbered clauses (handles indented draft text)
    for line in text.splitlines():
        stripped = line.strip()
        m = _NUMBERED.match(stripped)
        if m:
            _add(f"{m.group(1)} {m.group(2).strip()}")

    # Paragraph fallback: double-newline blocks with legal markers
    if len(clauses) < 2:
        for para in re.split(r"\n\s*\n+", text):
            para = para.strip()
            if len(para) < 40:
                continue
            if re.search(
                r"(shall|hereby|जाईल|येतो|अधिकार|jurisdiction|शिष्यवृत्ती|scholarship)",
                para,
                re.IGNORECASE,
            ):
                _add(para)

    return clauses[:max_clauses]


def format_clauses_for_prompt(clauses: List[str]) -> str:
    if not clauses:
        return ""
    lines = ["DRAFT OPERATIVE CLAUSES (for clause-level alignment):"]
    for i, clause in enumerate(clauses, start=1):
        lines.append(f"  [Draft Clause {i}] {clause[:500]}")
    return "\n".join(lines) + "\n"
