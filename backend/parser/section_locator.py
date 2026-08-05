"""
Position-aware GR section locators for template compliance checking.

Reuses regex patterns from section_patterns; complements rule_extractor which
extracts header metadata values without recording offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional

from parser.section_patterns import (
    BUDGET_HEAD_RE,
    DEPARTMENT_RE,
    DOC_TYPE_RE,
    FINANCIAL_SANCTION_RE,
    GOVT_LINE_EN_RE,
    GOVT_LINE_RE,
    GR_NUMBER_RE,
    OPERATIVE_CLAUSE_RE,
    OPERATIVE_FALLBACK_RE,
    OPERATIVE_HEADING_RE,
    PREAMBLE_SECTION_RE,
    PREAMBLE_START_RE,
    REF_SECTION_START_RE,
    SIGNATORY_RE,
    SUBJECT_LABEL_RE,
    SUBJECT_STOP,
)


@dataclass(frozen=True)
class SectionMatch:
    section_id: str
    char_offset: int
    line_number: int  # 1-based
    matched_text: str
    end_offset: int


def char_offset_to_line(text: str, offset: int) -> int:
    line = 1
    for i, ch in enumerate(text):
        if i >= offset:
            break
        if ch == "\n":
            line += 1
    return line


def _line_start_offset(text: str, line_number: int) -> int:
    if line_number <= 1:
        return 0
    count = 1
    for i, ch in enumerate(text):
        if ch == "\n":
            count += 1
            if count == line_number:
                return i + 1
    return 0


def _match_at(
    section_id: str,
    text: str,
    start: int,
    end: int,
    pattern: re.Pattern[str],
) -> Optional[SectionMatch]:
    search_text = text[start:end]
    m = pattern.search(search_text)
    if not m:
        return None
    abs_start = start + m.start()
    abs_end = start + m.end()
    return SectionMatch(
        section_id=section_id,
        char_offset=abs_start,
        line_number=char_offset_to_line(text, abs_start),
        matched_text=text[abs_start:abs_end].strip(),
        end_offset=abs_end,
    )


def locate_header_block(text: str) -> Optional[SectionMatch]:
    """Header: government line + document type or GR number in the opening block."""
    header_end = min(len(text), 4000)
    header = text[:header_end]

    candidates: List[SectionMatch] = []

    for pattern, sid in (
        (GOVT_LINE_RE, "header_block"),
        (GOVT_LINE_EN_RE, "header_block"),
        (DOC_TYPE_RE, "header_block"),
    ):
        m = pattern.search(header)
        if m:
            candidates.append(
                SectionMatch(
                    section_id="header_block",
                    char_offset=m.start(),
                    line_number=char_offset_to_line(text, m.start()),
                    matched_text=header[m.start() : m.end()].strip(),
                    end_offset=m.end(),
                )
            )

    m = GR_NUMBER_RE.search(header)
    if m:
        candidates.append(
            SectionMatch(
                section_id="header_block",
                char_offset=m.start(),
                line_number=char_offset_to_line(text, m.start()),
                matched_text=header[m.start() : m.end()].strip(),
                end_offset=m.end(),
            )
        )

    if not candidates:
        return None

    return min(candidates, key=lambda c: c.char_offset)


def locate_subject_line(text: str) -> Optional[SectionMatch]:
    """Subject: explicit विषय label or title lines before the government header."""
    lines = text.splitlines()
    offset = 0

    for i, raw in enumerate(lines[:35]):
        line = raw.strip()
        line_len = len(raw) + 1  # include newline

        m = SUBJECT_LABEL_RE.match(line)
        if m:
            snippet = line
            if m.group(1).strip():
                snippet = line
            else:
                parts = [line]
                for nxt in lines[i + 1 : i + 6]:
                    if not nxt.strip():
                        break
                    if any(nxt.startswith(s) or s in nxt[:12] for s in SUBJECT_STOP):
                        break
                    if re.match(r"^(वाचा|बाचा|संदर्भ|प्रस्तावना|दिनांक)", nxt):
                        break
                    parts.append(nxt.strip())
                snippet = " ".join(parts)

            return SectionMatch(
                section_id="subject_line",
                char_offset=offset,
                line_number=i + 1,
                matched_text=snippet.strip(),
                end_offset=offset + len(snippet),
            )

        offset += line_len

    # Title block before महाराष्ट्र शासन
    offset = 0
    title_parts: List[str] = []
    title_start = 0
    for i, raw in enumerate(lines[:20]):
        line = raw.strip()
        if GOVT_LINE_RE.search(line) and "राजपत्र" not in line:
            if title_parts:
                snippet = " ".join(title_parts).strip()
                return SectionMatch(
                    section_id="subject_line",
                    char_offset=title_start,
                    line_number=char_offset_to_line(text, title_start),
                    matched_text=snippet,
                    end_offset=title_start + len(snippet),
                )
            break
        if any(t in line for t in ("शासन निर्णय", "शासन पत्र")) and re.search(r"क्र", line):
            break
        if line.startswith(("वाचा", "संदर्भ", "प्रस्तावना")):
            break
        if line:
            if not title_parts:
                title_start = offset
            title_parts.append(line)
        offset += len(raw) + 1

    return None


def locate_references_section(text: str) -> Optional[SectionMatch]:
    return _match_at(
        "references_section",
        text,
        0,
        min(len(text), 8000),
        REF_SECTION_START_RE,
    )


def locate_operative_section(text: str) -> Optional[SectionMatch]:
    """Operative/decision paragraphs after header and references."""
    search_from = 0
    ref = locate_references_section(text)
    if ref:
        search_from = ref.end_offset
    else:
        preamble = _match_at(
            "operative_section",
            text,
            0,
            len(text),
            PREAMBLE_START_RE,
        )
        if preamble:
            search_from = preamble.char_offset

    for pattern in (OPERATIVE_HEADING_RE, OPERATIVE_FALLBACK_RE, OPERATIVE_CLAUSE_RE):
        hit = _match_at(
            "operative_section",
            text,
            search_from,
            len(text),
            pattern,
        )
        if hit:
            return hit

    return None


def locate_preamble_section(text: str) -> Optional[SectionMatch]:
    """Preamble / background language preceding the operative decision."""
    m = PREAMBLE_SECTION_RE.search(text)
    if not m:
        return None
    return SectionMatch(
        section_id="preamble_section",
        char_offset=m.start(),
        line_number=char_offset_to_line(text, m.start()),
        matched_text=m.group(0).strip(),
        end_offset=m.end(),
    )


def locate_financial_sanction_block(text: str) -> Optional[SectionMatch]:
    """Funding / sanction language used to authorize the expense."""
    for pattern in (FINANCIAL_SANCTION_RE,):
        m = pattern.search(text)
        if m:
            return SectionMatch(
                section_id="financial_sanction_block",
                char_offset=m.start(),
                line_number=char_offset_to_line(text, m.start()),
                matched_text=text[m.start() : min(len(text), m.start() + 220)].strip(),
                end_offset=min(len(text), m.start() + 220),
            )
    return None


def locate_budget_head(text: str) -> Optional[SectionMatch]:
    """Look for budget head or accounting head references in the sanction block."""
    m = BUDGET_HEAD_RE.search(text)
    if not m:
        return None
    return SectionMatch(
        section_id="budget_head",
        char_offset=m.start(),
        line_number=char_offset_to_line(text, m.start()),
        matched_text=m.group(0).strip(),
        end_offset=m.end(),
    )


def locate_signatory_block(text: str) -> Optional[SectionMatch]:
    """Signatory closing block — searched in the tail of the document."""
    lines = text.splitlines()
    if not lines:
        return None

    tail_start_line = max(0, len(lines) - 45)
    tail_offset = _line_start_offset(text, tail_start_line + 1)
    tail = text[tail_offset:]

    m = SIGNATORY_RE.search(tail)
    if m:
        abs_start = tail_offset + m.start()
        abs_end = tail_offset + m.end()
        return SectionMatch(
            section_id="signatory_block",
            char_offset=abs_start,
            line_number=char_offset_to_line(text, abs_start),
            matched_text=text[abs_start:abs_end].strip(),
            end_offset=abs_end,
        )

    # Weaker fallback: department + secretary line in tail
    for i in range(tail_start_line, len(lines)):
        line = lines[i].strip()
        if DEPARTMENT_RE.search(line) and i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if re.search(r"(सचिव|Secretary)", nxt, re.IGNORECASE):
                offset = _line_start_offset(text, i + 1)
                snippet = f"{line}\n{nxt}"
                return SectionMatch(
                    section_id="signatory_block",
                    char_offset=offset,
                    line_number=i + 1,
                    matched_text=snippet,
                    end_offset=offset + len(snippet),
                )

    return None


LOCATORS: dict[str, Callable[[str], Optional[SectionMatch]]] = {
    "header_block": locate_header_block,
    "subject_line": locate_subject_line,
    "preamble_section": locate_preamble_section,
    "references_section": locate_references_section,
    "operative_section": locate_operative_section,
    "financial_sanction_block": locate_financial_sanction_block,
    "budget_head": locate_budget_head,
    "signatory_block": locate_signatory_block,
}


def locate_section(section_id: str, text: str) -> Optional[SectionMatch]:
    fn = LOCATORS.get(section_id)
    if fn is None:
        return None
    return fn(text)
