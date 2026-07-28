"""
Rule-based GR metadata extractor (no LLM).

Searches only the document header / first page.
Returns GRMetadata with None for fields it cannot find.
"""

from __future__ import annotations

import re
from typing import List, Optional

from parser.metadata import GRMetadata


# Fields the hybrid pipeline treats as required for a complete rule extraction.
CORE_FIELDS = (
    "document_type",
    "department",
    "gr_number",
    "date",
    "subject",
)

DOCUMENT_TYPES = (
    "शासन पूरक पत्र",
    "शासन परिपत्रक",
    "शासन निर्णय",
    "शासन पत्र",
    "कार्यालयीन आदेश",
    "शासन आदेश",
    "अधिसूचना",
)

# Longer phrases first so "शासन पूरक पत्र" wins over "शासन पत्र".
_DOC_TYPE_RE = re.compile(
    r"(शासन\s*पूरक\s*पत्र|शासन\s*परिपत्रक|शासन\s*निर्णय|"
    r"शासन\s*पत्र|कार्यालयीन\s*आदेश|शासन\s*आदेश|अधिसूचना)"
)

_MARATHI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_MONTHS = {
    "जानेवारी": 1,
    "फेब्रुवारी": 2,
    "मार्च": 3,
    "एप्रिल": 4,
    "मे": 5,
    "जून": 6,
    "जुलै": 7,
    "जुले": 7,
    "ऑगस्ट": 8,
    "सप्टेंबर": 9,
    "ऑक्टोबर": 10,
    "नोव्हेंबर": 11,
    "डिसेंबर": 12,
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_SUBJECT_STOP = (
    "महाराष्ट्र शासन",
    "महाराष्ट् शासन",
    "महाराष्ट॒ शासन",
    "वाचा",
    "बाचा",
    "संदर्भ",
    "प्रस्तावना",
    "दिनांक",
    "शासन निर्णय",
    "शासन पत्र",
    "शासन परिपत्रक",
    "शासन आदेश",
    "कार्यालयीन आदेश",
    "अधिसूचना",
)


def _header_lines(text: str, max_lines: int = 60) -> List[str]:
    """Non-empty lines from the top of the document (first page / header)."""

    lines: List[str] = []
    blank_streak = 0
    seen_refs = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            blank_streak += 1
            if lines and blank_streak >= 3:
                break
            continue

        blank_streak = 0
        lines.append(line)

        if re.match(r"^(वाचा|बाचा|संदर्भ)(?:\s|[.:ः\-–—]|$)", line) or re.match(
            r"^Reference(?:\s|[.:\-–—]|$)", line, re.IGNORECASE
        ):
            seen_refs = True

        # Stop at body, but only after we have had a chance to capture refs
        if any(s in line for s in ("प्रस्तावना",)) and len(lines) > 8:
            break
        if seen_refs and re.match(
            r"^शासन\s*(निर्णय|परिपत्रक|आदेश)\s*[:：\-]", line
        ):
            break

        if len(lines) >= max_lines:
            break

    return lines


def _header_text(lines: List[str]) -> str:
    return "\n".join(lines)


def _clean_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


_REF_ITEM_START = re.compile(
    r"^[\(]?"
    r"[०१२३४५६७८९0-9]{1,3}"
    r"[\.\)\]]\s*"
)

_REF_SECTION_START = re.compile(
    r"^(वाचा|बाचा|संदर्भ|Reference)(?:\s|[.:ः\-–—]|$)",
    re.IGNORECASE,
)

_REF_SECTION_STOP = re.compile(
    r"^(प्रस्तावना|शासन\s*निर्णय\s*[:：\-]|शासन\s*परिपत्रक\s*[:：\-]|"
    r"परिपत्रक\s*[:：\-]|आदेश\s*[:：\-]|शासन\s*आदेश\s*[:：\-])"
)


def _ref_date(raw: str) -> Optional[str]:
    """Best-effort date from a reference line (prefer last दि./दिनांक)."""

    candidates: List[str] = []

    # Keep year even when written as "दि. १४ मे, २०१९"
    for m in re.finditer(
        r"(?:दिनांक|दिनाक|दि)\s*[.:ः\-–—]*\s*"
        r"([०१२३४५६७८९0-9]{1,2}\s*[^\d]{0,20}?,?\s*[०१२३४५६७८९0-9]{4}"
        r"|[०१२३४५६७८९0-9]{1,2}[./\-][०१२३४५६७८९0-9]{1,2}[./\-][०१२३४५६७८९0-9]{4}"
        r"|[०१२३४५६७८९0-9]{1,2}\s*[A-Za-zअ-ह][^\d]{2,20}?,?\s*[०१२३४५६७८९0-9]{4})",
        raw,
        re.IGNORECASE,
    ):
        candidates.append(m.group(1))

    for m in re.finditer(
        r"[०१२३४५६७८९0-9]{1,2}[./\-][०१२३४५६७८९0-9]{1,2}[./\-][०१२३४५६७८९0-9]{4}",
        raw,
    ):
        candidates.append(m.group(0))

    parsed = None
    for c in candidates:
        hit = _parse_date_string(c)
        if hit:
            parsed = hit
    return parsed


def extract_references(lines: List[str]) -> list:
    """
    Extract वाचा / संदर्भ entries as [{raw, date}, ...].
    """

    block: List[str] = []
    in_section = False

    for line in lines:
        if not in_section:
            if not _REF_SECTION_START.match(line):
                continue
            in_section = True
            rest = re.sub(
                r"^(वाचा|बाचा|संदर्भ|Reference)\s*[.:ः\-–—]*\s*",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()
            if rest:
                block.append(rest)
            continue

        if _REF_SECTION_STOP.match(line):
            break
        # Body decision heading without being a numbered ref
        if re.match(r"^शासन\s*(निर्णय|परिपत्रक|आदेश)\s*[:：\-]", line) and not _REF_ITEM_START.match(line):
            break
        block.append(line)

    if not block:
        return []

    items: List[str] = []
    current: List[str] = []

    for line in block:
        if _REF_ITEM_START.match(line):
            if current:
                items.append(" ".join(current))
            current = [line]
        else:
            if current:
                current.append(line)
            else:
                # Unnumbered single reference under वाचा
                current = [line]

    if current:
        items.append(" ".join(current))

    results = []
    for item in items:
        raw = _clean_spaces(item)
        # Drop empty / tiny OCR junk
        if len(raw) < 8:
            continue
        results.append(
            {
                "raw": raw,
                "date": _ref_date(raw),
            }
        )

    return results


def extract_document_type(lines: List[str]) -> Optional[str]:
    """First matching document type in the header (not deep body)."""

    for line in lines[:30]:
        if re.search(r"(क्रमांक|कमांक|क्र\s*\.|क्र\s*:|No\.)", line, re.IGNORECASE):
            match = _DOC_TYPE_RE.search(line)
            if match:
                return _clean_spaces(match.group(1))
            if re.search(r"\bparipatrak\b|circular", line, re.IGNORECASE):
                return "शासन परिपत्रक"
            if re.search(r"Government\s+Resolution", line, re.IGNORECASE):
                return "शासन निर्णय"
            if re.search(r"\bNotification\b", line, re.IGNORECASE):
                return "अधिसूचना"
            # Bare परिपत्रक क्रमांक
            if re.match(r"परिपत्रक\s*क्र", line):
                return "शासन परिपत्रक"

    for line in lines[:25]:
        if re.search(r"शासन\s*निर्णय\s*[:：\-]", line) and "क्र" not in line:
            continue
        match = _DOC_TYPE_RE.search(line)
        if match:
            return _clean_spaces(match.group(1))

    return None


_GOVT_LINE_RE = re.compile(r"महाराष्ट\S*\s*शासन")


def extract_department(lines: List[str]) -> Optional[str]:
    """Department line near 'महाराष्ट्र शासन' / GOVERNMENT OF MAHARASHTRA."""

    for i, line in enumerate(lines[:35]):
        is_govt = bool(_GOVT_LINE_RE.search(line)) or bool(
            re.search(r"GOVERNMENT\s+OF\s+MAHARASHTRA", line, re.IGNORECASE)
        )
        if not is_govt:
            continue
        if "राजपत्र" in line:
            continue

        same = re.split(
            r"(?:महाराष्ट\S*\s*शासन|GOVERNMENT\s+OF\s+MAHARASHTRA)\s*[,:]?\s*",
            line,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        if len(same) == 2 and same[1].strip() and re.search(
            r"(विभाग|विश्राग|खाते|Department)", same[1], re.IGNORECASE
        ):
            return _clean_spaces(same[1].strip(" ,;."))

        for j in range(i + 1, min(i + 5, len(lines))):
            nxt = lines[j].strip().strip(" ,;.")
            if not nxt:
                continue
            if _GOVT_LINE_RE.search(nxt) or re.search(
                r"GOVERNMENT\s+OF\s+MAHARASHTRA", nxt, re.IGNORECASE
            ):
                continue
            if re.match(r"^(दिनांक|दि\s*\.|दिनाक|Date)\b", nxt, re.IGNORECASE):
                continue
            if re.search(r"(क्रमांक|कमांक|क्र\s*\.|क्र\s*:|No\.)", nxt) and re.search(
                r"(शासन|अधिसूचना|आदेश|Government|Resolution|Circular)",
                nxt,
                re.IGNORECASE,
            ):
                continue
            if "मंत्रालय" in nxt and not re.search(r"(विभाग|विश्राग)", nxt):
                continue
            if re.search(r"(विभाग|विश्राग|खाते|Department)", nxt, re.IGNORECASE) or (
                len(nxt) >= 8 and not nxt.startswith(("वाचा", "संदर्भ", "प्रस्तावना"))
            ):
                if nxt.startswith(("वाचा", "संदर्भ", "प्रस्तावना", "आदेश", "Preamble")):
                    continue
                return _clean_spaces(nxt)

    return None


def extract_gr_number(lines: List[str]) -> Optional[str]:
    """
    Official number after क्रमांक / क्र. / कमांक / No.
    Returns the identifier only (no 'शासन निर्णय' / 'क्रमांक' prefix).
    """

    patterns = [
        # शासन निर्णय, क्रमांक : ... / शासन निर्णय क्र. ...
        re.compile(
            r"(?:शासन\s*(?:निर्णय|पत्र|परिपत्रक|आदेश|पूरक\s*पत्र)|"
            r"कार्यालयीन\s*आदेश|अधिसूचना|परिपत्रक)"
            r"\s*,?\s*(?:क्रमांक|कमांक|क्र)\s*[.:ः\-–—]*\s*(.+)$"
        ),
        # English headers
        re.compile(
            r"(?:Government\s+Resolution|Government\s+Circular|"
            r"Government\s+Order|Notification)"
            r"\s*No\.?\s*[:\-–—]?\s*(.+)$",
            re.IGNORECASE,
        ),
        # Standalone क्रमांक : ...
        re.compile(r"^(?:क्रमांक|कमांक)\s*[.:ः\-–—]*\s*(.+)$"),
        # क्र. ... / क्र : ...
        re.compile(r"^क्र\s*[.:ः\-–—]+\s*(.+)$"),
    ]

    for line in lines[:35]:
        for pattern in patterns:
            match = pattern.search(line)
            if not match:
                continue
            value = match.group(1).strip()
            value = re.split(r"\s{2,}|\t", value)[0].strip(" .;,-")
            if value and not re.fullmatch(r"[:：\-–—]+", value):
                return _clean_spaces(value)

    return None


def _to_english_digits(text: str) -> str:
    return text.translate(_MARATHI_DIGITS)


def _parse_date_string(raw: str) -> Optional[str]:
    """Convert common Marathi/English GR dates to YYYY-MM-DD."""

    raw = _clean_spaces(_to_english_digits(raw))
    raw = re.sub(r"[\"“”'`]", "", raw)
    raw = raw.strip(" .;,-")

    # 14.11.2019 / 14/11/2019 / 14-11-2019
    m = re.search(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b", raw)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    # 14 नोव्हेंबर, 2019 / 11 मार्च 2020 / 6जून, 2001
    month_alt = "|".join(sorted((re.escape(k) for k in _MONTHS), key=len, reverse=True))
    m = re.search(
        rf"(\d{{1,2}})\s*({month_alt})\s*,?\s*(\d{{4}})",
        raw,
        re.IGNORECASE,
    )
    if m:
        d = int(m.group(1))
        month_key = m.group(2)
        mo = _MONTHS.get(month_key) or _MONTHS.get(month_key.lower())
        y = int(m.group(3))
        if mo and 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"

    return None


def extract_date(lines: List[str]) -> Optional[str]:
    """Issue date after दिनांक / दि. / Date in the header."""

    for line in lines[:35]:
        if "दिनांक व कोड" in line or "पत्राचा क्रमांक" in line:
            continue

        m = re.search(
            r"(?:^|\s)(?:दिनांक|दिनाक|दि|Date)\s*[.:ः\-–—]*\s*(.+)$",
            line,
            re.IGNORECASE,
        )
        if not m:
            continue

        parsed = _parse_date_string(m.group(1))
        if parsed:
            return parsed

        parsed = _parse_date_string(line)
        if parsed:
            return parsed

    return None


def extract_subject(lines: List[str]) -> Optional[str]:
    """
    Subject after 'विषय', or title lines above 'महाराष्ट्र शासन' if present.
    """

    # 1) Explicit विषय label
    for i, line in enumerate(lines[:30]):
        m = re.match(r"विषय\s*[.:ः\-–—]*\s*(.*)$", line)
        if not m:
            continue

        parts: List[str] = []
        first = m.group(1).strip()
        if first:
            parts.append(first)

        for nxt in lines[i + 1 : i + 8]:
            if not nxt.strip():
                break
            if any(nxt.startswith(s) or s in nxt[:12] for s in _SUBJECT_STOP):
                break
            if re.match(r"^(वाचा|बाचा|संदर्भ|प्रस्तावना|दिनांक)", nxt):
                break
            parts.append(nxt.strip())

        if parts:
            return _clean_spaces(" ".join(parts))

    # 2) Fallback: lines before महाराष्ट्र शासन (common GR title block)
    title: List[str] = []
    for line in lines[:20]:
        if _GOVT_LINE_RE.search(line) and "राजपत्र" not in line:
            break
        if any(t in line for t in DOCUMENT_TYPES) and re.search(r"क्र", line):
            break
        if line.startswith(("वाचा", "संदर्भ", "प्रस्तावना")):
            break
        title.append(line)

    if title:
        return _clean_spaces(" ".join(title))

    return None


def rule_extract(text: str, filename: Optional[str] = None) -> GRMetadata:
    """
    Extract metadata with regex/heuristics only.
    Missing values remain None. references defaults to [].
    """

    lines = _header_lines(text)

    return GRMetadata(
        filename=filename,
        document_type=extract_document_type(lines),
        department=extract_department(lines),
        gr_number=extract_gr_number(lines),
        date=extract_date(lines),
        subject=extract_subject(lines),
        references=extract_references(lines),
    )


def has_reference_section(text: str) -> bool:
    """True if header looks like it contains वाचा / संदर्भ."""

    for line in _header_lines(text)[:40]:
        if _REF_SECTION_START.match(line):
            return True
    return False


def get_missing_fields(metadata: GRMetadata, text: str | None = None) -> List[str]:
    """
    Return CORE_FIELDS that are still None / empty.
    If text is given and a वाचा/संदर्भ section exists but references=[],
    also request LLM fill for references.
    """

    missing: List[str] = []
    data = metadata.model_dump() if hasattr(metadata, "model_dump") else dict(metadata)

    for field in CORE_FIELDS:
        value = data.get(field)
        if value is None:
            missing.append(field)
        elif isinstance(value, str) and not value.strip():
            missing.append(field)

    refs = data.get("references") or []
    if not refs and text is not None and has_reference_section(text):
        missing.append("references")

    return missing
