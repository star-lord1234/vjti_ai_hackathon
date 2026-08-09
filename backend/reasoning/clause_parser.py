"""
Clause-level parsing for draft GR text (operative provisions).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Set

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


def _clause_hash(text: str) -> str:
    """8-char SHA-256 fingerprint of a normalized clause string."""
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:8]


@dataclass
class ClauseDiff:
    """Result of a clause-level diff between two draft versions."""

    added: List[str] = field(default_factory=list)
    """Clauses that are new in the current version (not present in previous)."""

    modified: List[str] = field(default_factory=list)
    """Clauses whose content changed relative to the previous version
    (same position index, different text)."""

    unchanged: List[str] = field(default_factory=list)
    """Clauses whose content is identical to the previous version."""

    @property
    def changed(self) -> List[str]:
        """Union of added and modified clauses — the ones that need re-checking."""
        return self.added + self.modified

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified)


def diff_clauses(previous_text: str, current_text: str) -> ClauseDiff:
    """
    Compare two draft texts at clause granularity.

    A clause is considered **unchanged** when its content hash matches any
    clause hash from the previous version.  A clause is **modified** when it
    occupies the same position index as a previous clause but the text
    differs.  A clause is **added** when it has no counterpart (by position)
    in the previous version.

    This means:
    - If the user only changed the amount in clause 1, only clause 1 is
      returned in ``changed``; clauses 2, 3, … are in ``unchanged``.
    - If the user appended a new clause 4, only clause 4 is in ``added``.
    - Reordering is treated conservatively (position-based) so that a
      reordered clause whose text is identical elsewhere is still seen as
      unchanged at the global hash level.
    """
    prev_clauses = extract_draft_clauses(previous_text)
    curr_clauses = extract_draft_clauses(current_text)

    # Build a set of all previous clause hashes for O(1) unchanged detection
    prev_hashes: Set[str] = {_clause_hash(c) for c in prev_clauses}

    result = ClauseDiff()
    for idx, clause in enumerate(curr_clauses):
        h = _clause_hash(clause)
        if h in prev_hashes:
            # Content-identical to some previous clause → unchanged regardless of position
            result.unchanged.append(clause)
        elif idx < len(prev_clauses):
            # Same position slot existed before but content changed → modified
            result.modified.append(clause)
        else:
            # Position didn't exist in previous version → entirely new clause
            result.added.append(clause)

    return result
