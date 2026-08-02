"""
Deterministic rule-based signals to complement LLM conflict detection.
Uses rule_extractor metadata plus regex overlap on amounts, dates, jurisdiction.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set

from parser.rule_extractor import rule_extract

_AMOUNT_RE = re.compile(
    r"(?:₹|Rs\.?|Rupees?|रुपये?)\s*[\d,०१२३४५६७८९]+|"
    r"[\d,०१२३४५६७८९]+\s*(?:lakh|lakhs|crore|crores|लाख|कोटी)",
    re.IGNORECASE,
)
_JURISDICTION_TERMS = (
    "exclusive jurisdiction",
    "EXCLUSIVE JURISDICTION",
    "environmental impact",
    "EIA",
    "nodal ministry",
    "state authority",
    "केंद्र",
    "राज्य अधिकार",
)
_DATE_RE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\b\d{1,2}[./\-]\d{1,2}[./\-]\d{4}\b|"
    r"(?:जानेवारी|फेब्रुवारी|मार्च|एप्रिल|मे|जून|जुलै|ऑगस्ट|"
    r"सप्टेंबर|ऑक्टोबर|नोव्हेंबर|डिसेंबर|january|february|march|"
    r"april|may|june|july|august|september|october|november|december)",
    re.IGNORECASE,
)


def _normalize_dept(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _token_overlap(a: str, b: str) -> float:
    ta = {t for t in re.split(r"\W+", a.lower()) if len(t) >= 4}
    tb = {t for t in re.split(r"\W+", b.lower()) if len(t) >= 4}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def extract_rule_signals(
    draft_text: str,
    retrieved: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """
    Return deterministic signals as dicts {signal_type, value, note, matched_gr_id}.
    """
    signals: List[Dict[str, str]] = []
    draft_meta = rule_extract(draft_text)
    draft_dept = _normalize_dept(draft_meta.department)
    draft_subject = (draft_meta.subject or "").strip()

    # Header metadata signals
    if draft_meta.gr_number:
        signals.append(
            {
                "signal_type": "draft_gr_number",
                "value": draft_meta.gr_number,
                "note": "Rule-extracted draft GR number from header.",
                "matched_gr_id": "",
            }
        )
    if draft_meta.date:
        signals.append(
            {
                "signal_type": "draft_date",
                "value": draft_meta.date,
                "note": "Rule-extracted draft issue date.",
                "matched_gr_id": "",
            }
        )

    # Amount overlaps
    draft_amounts = _AMOUNT_RE.findall(draft_text)
    for amount in set(draft_amounts[:5]):
        for row in retrieved[:10]:
            ocr = (row.get("matched_chunk_text") or row.get("subject_mr") or "")[:2000]
            if amount.lower() in ocr.lower() or amount in str(row.get("subject_mr") or ""):
                signals.append(
                    {
                        "signal_type": "amount_overlap",
                        "value": amount,
                        "note": f"Financial amount also appears in retrieved GR context.",
                        "matched_gr_id": str(row.get("id") or ""),
                    }
                )
                break

    # Jurisdiction keyword overlaps
    draft_lower = draft_text.lower()
    for term in _JURISDICTION_TERMS:
        if term.lower() in draft_lower:
            for row in retrieved[:10]:
                hay = f"{row.get('subject_mr') or ''} {row.get('matched_chunk_text') or ''}"
                if term.lower() in hay.lower():
                    signals.append(
                        {
                            "signal_type": "jurisdiction_overlap",
                            "value": term,
                            "note": "Jurisdiction keyword found in draft and corpus hit.",
                            "matched_gr_id": str(row.get("id") or ""),
                        }
                    )
                    break

    # Date mentions in draft body
    for date_match in set(_DATE_RE.findall(draft_text)[:5]):
        for row in retrieved[:8]:
            if date_match in str(row.get("gr_date") or ""):
                signals.append(
                    {
                        "signal_type": "date_overlap",
                        "value": date_match,
                        "note": "Draft date reference aligns with retrieved GR date field.",
                        "matched_gr_id": str(row.get("id") or ""),
                    }
                )
                break

    # Department alignment / mismatch
    if draft_dept:
        for row in retrieved[:10]:
            corpus_dept = _normalize_dept(row.get("department"))
            if not corpus_dept:
                continue
            overlap = _token_overlap(draft_dept, corpus_dept)
            if overlap >= 0.35:
                signals.append(
                    {
                        "signal_type": "department_match",
                        "value": row.get("department") or "",
                        "note": "Draft department aligns with retrieved GR department.",
                        "matched_gr_id": str(row.get("id") or ""),
                    }
                )
            elif overlap < 0.1 and draft_subject:
                signals.append(
                    {
                        "signal_type": "department_mismatch",
                        "value": f"draft={draft_meta.department} vs corpus={row.get('department')}",
                        "note": "Cross-departmental policy overlap candidate.",
                        "matched_gr_id": str(row.get("id") or ""),
                    }
                )

    # Subject keyword overlap with top retrieval hit
    if draft_subject and retrieved:
        top = retrieved[0]
        subj = str(top.get("subject_mr") or "")
        if _token_overlap(draft_subject, subj) >= 0.2:
            signals.append(
                {
                    "signal_type": "subject_overlap",
                    "value": subj[:120],
                    "note": "Draft subject overlaps top retrieved GR subject.",
                    "matched_gr_id": str(top.get("id") or ""),
                }
            )

    # Deduplicate by type+value
    seen: Set[str] = set()
    unique: List[Dict[str, str]] = []
    for sig in signals:
        key = f"{sig['signal_type']}:{sig['value']}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(sig)
    return unique


def format_rule_signals_for_prompt(signals: List[Dict[str, str]]) -> str:
    if not signals:
        return ""
    lines = ["DETERMINISTIC RULE SIGNALS (verify against context — do not ignore):"]
    for sig in signals[:15]:
        gr = sig.get("matched_gr_id") or "n/a"
        lines.append(
            f"  - [{sig['signal_type']}] {sig['value'][:100]} "
            f"(GR id {gr}): {sig['note']}"
        )
    return "\n".join(lines) + "\n"
