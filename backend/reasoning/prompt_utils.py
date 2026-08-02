"""
Prompt budgeting, citation validation, and temporal helpers for LLM reasoning.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple, TypeVar

from reasoning.models import ConflictFinding, ConflictPair, QueryAnswer, SupportingGR

T = TypeVar("T")

# Groq on-demand tier ≈12k TPM per request — budget input conservatively for Marathi OCR.
GROQ_MAX_INPUT_TOKENS = int(os.getenv("GROQ_MAX_INPUT_TOKENS", "9000"))
# Devanagari / mixed Marathi-English tokenizes denser than ~4 chars/token.
CHARS_PER_TOKEN = float(os.getenv("REASONING_CHARS_PER_TOKEN", "2.2"))

_default_prompt_chars = int(GROQ_MAX_INPUT_TOKENS * CHARS_PER_TOKEN)
MAX_PROMPT_CHARS = int(os.getenv("REASONING_MAX_PROMPT_CHARS", str(_default_prompt_chars)))
MAX_DRAFT_CHARS = int(os.getenv("REASONING_MAX_DRAFT_CHARS", "2500"))
CONFLICT_DRAFT_CHARS = int(os.getenv("CONFLICT_MAX_DRAFT_CHARS", "2000"))
CONFLICT_CONTEXT_CHARS = int(os.getenv("CONFLICT_MAX_CONTEXT_CHARS", "5500"))
CONFLICT_EXCERPT_CHARS = int(os.getenv("CONFLICT_EXCERPT_CHARS", "700"))
COMPARE_OCR_CHARS = int(os.getenv("REASONING_COMPARE_OCR_CHARS", "4000"))
REASONING_TEMPERATURE = float(os.getenv("REASONING_TEMPERATURE", "0"))
UNPARSEABLE_CONFIDENCE = float(os.getenv("REASONING_UNPARSEABLE_CONFIDENCE", "0.5"))

# Compact JSON shapes — avoids bloated model_json_schema() in every system prompt.
CONFLICT_OUTPUT_SCHEMA = (
    '{"conflicting":bool,"explanation":str,"conflicting_clauses":[str],'
    '"affected_grs":[{"label":str,"gr_number_canonical":str|null,'
    '"relevance_note":str|null,"corpus_excerpt":str|null}],'
    '"cross_departmental":bool,"supersession_detected":bool,"confidence":float}'
)
QUERY_OUTPUT_SCHEMA = (
    '{"answer":str,"supporting_grs":[{"label":str,"gr_number_canonical":str|null,'
    '"relevance_note":str|null}],"confidence":float}'
)
COMPARE_OUTPUT_SCHEMA = (
    '{"summary":str,"added":[str],"removed":[str],"changed":[str],'
    '"contradictions":[str],"confidence":float}'
)


def parse_gr_date(value: Any) -> Optional[date]:
    """Parse gr_date field to date for sorting."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text or text.lower() == "unknown":
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except ValueError:
        return None


def sort_results_by_recency(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort hybrid search results newest-first for supersession-aware reasoning.
    Vector score breaks ties when dates are equal or missing.
    """
    def sort_key(r: Dict[str, Any]) -> Tuple[int, float, int]:
        d = parse_gr_date(r.get("gr_date"))
        date_ord = d.toordinal() if d else 0
        score = float(r.get("score") or 0.0)
        doc_id = int(r.get("id") or 0)
        return (date_ord, score, -doc_id)

    return sorted(results, key=sort_key, reverse=True)


def build_ocr_excerpt_with_context(
    full_ocr: str,
    matched_chunk: Optional[str],
    max_chars: int,
) -> str:
    """
    Build an OCR excerpt centered on the matched chunk when possible,
    otherwise use a larger prefix of the document body.
    """
    text = (full_ocr or "").strip()
    if not text:
        return ""

    needle = (matched_chunk or "").strip()
    if needle and needle in text:
        idx = text.index(needle)
        half = max(max_chars // 2, max_chars - len(needle))
        start = max(0, idx - half // 2)
        end = min(len(text), start + max_chars)
        if end - start < max_chars:
            start = max(0, end - max_chars)
        excerpt = text[start:end].strip()
        if start > 0:
            excerpt = "... [truncated] " + excerpt
        if end < len(text):
            excerpt = excerpt + " ... [truncated]"
        return excerpt

    if len(text) <= max_chars:
        return text

    # Head + tail when no matched chunk
    head = int(max_chars * 0.6)
    tail = max_chars - head - 40
    return (
        text[:head].rstrip()
        + "\n\n[... middle omitted ...]\n\n"
        + text[-tail:].lstrip()
    )


def summarize_draft_for_prompt(draft: str, max_chars: int = MAX_DRAFT_CHARS) -> str:
    """Include head and tail of draft so body clauses are not lost."""
    text = draft.strip()
    if len(text) <= max_chars:
        return text

    head = int(max_chars * 0.55)
    tail = max_chars - head - 60
    return (
        text[:head].rstrip()
        + "\n\n[... draft middle omitted for length — retrieval used full text ...]\n\n"
        + text[-tail:].lstrip()
    )


def estimate_tokens(text: str) -> int:
    """Conservative token estimate for Marathi-heavy legal OCR."""
    return max(1, int(len(text) / CHARS_PER_TOKEN))


def estimate_chars_to_tokens(char_count: int) -> int:
    return estimate_tokens("x" * char_count)


def chars_for_token_budget(max_tokens: int) -> int:
    return max(1500, int(max_tokens * CHARS_PER_TOKEN))


def fit_prompt_pair(
    system_prompt: str,
    user_prompt: str,
    max_total_chars: Optional[int] = None,
) -> Tuple[str, str, bool]:
    """
    Ensure system + user prompts fit within char budget (derived from GROQ_MAX_INPUT_TOKENS).
    Truncates user_prompt from the middle if needed.
    Returns (system, user, was_truncated).
    """
    budget = max_total_chars if max_total_chars is not None else MAX_PROMPT_CHARS
    total = len(system_prompt) + len(user_prompt)
    if total <= budget:
        est = estimate_tokens(system_prompt + user_prompt)
        print(f"Prompt size: {total} chars (~{est} tokens, budget ~{int(budget / CHARS_PER_TOKEN)} tokens)")
        return system_prompt, user_prompt, False

    # Reserve system prompt; shrink user portion
    user_budget = max(1200, budget - len(system_prompt) - 200)
    head = int(user_budget * 0.45)
    tail = max(400, user_budget - head - 50)
    trimmed = (
        user_prompt[:head].rstrip()
        + "\n\n[... prompt truncated to fit Groq token limit ...]\n\n"
        + user_prompt[-tail:].lstrip()
    )
    est = estimate_tokens(system_prompt + trimmed)
    print(
        f"Warning: prompt truncated {len(user_prompt)}→{len(trimmed)} user chars "
        f"(~{est} tokens total, budget {budget} chars)."
    )
    return system_prompt, trimmed, True


_AMOUNT_TOKEN = re.compile(
    r"(?:₹|Rs\.?|Rupees?|रुपये?)\s*[\d,०१२३४५६७८९]+|"
    r"[\d,०१२३४५६७८९]+\s*(?:lakh|lakhs|crore|crores|लाख|कोटी)",
    re.IGNORECASE,
)


def _sentence_split(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?।\n])\s+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def _overlap_score(a: str, b: str) -> float:
    ta = {t for t in re.split(r"\W+", a.lower()) if len(t) >= 3}
    tb = {t for t in re.split(r"\W+", b.lower()) if len(t) >= 3}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def extract_corpus_excerpt_for_clause(
    draft_clause: str,
    ocr_text: str,
    matched_chunk: Optional[str] = None,
    max_chars: int = 400,
) -> str:
    """
    Find the best-matching sentence from corpus OCR for a draft conflicting clause.
    Prefers matched retrieval chunk, then token/amount overlap with OCR sentences.
    """
    clause = (draft_clause or "").strip()
    if not clause:
        return ""

    chunk = (matched_chunk or "").strip()
    if chunk and len(chunk) >= 25:
        if chunk in ocr_text:
            return chunk[:max_chars]
        return chunk[:max_chars]

    haystack = (ocr_text or "").strip()
    if not haystack:
        return chunk[:max_chars] if chunk else ""

    sentences = _sentence_split(haystack)
    if not sentences:
        return haystack[:max_chars]

    clause_amounts = _AMOUNT_TOKEN.findall(clause)
    best_sent = ""
    best_score = -1.0

    for sent in sentences:
        score = _overlap_score(clause, sent)
        if clause_amounts:
            for amt in clause_amounts:
                if amt.lower() in sent.lower():
                    score += 0.35
        if score > best_score:
            best_score = score
            best_sent = sent

    if best_sent:
        return best_sent[:max_chars]

    # Fallback: window around first amount match in full OCR
    if clause_amounts:
        for amt in clause_amounts:
            idx = haystack.lower().find(amt.lower())
            if idx >= 0:
                start = max(0, idx - 120)
                end = min(len(haystack), idx + max_chars)
                return haystack[start:end].strip()

    return (chunk or sentences[0])[:max_chars]


def _find_gr_for_clause(
    clause: str,
    affected_grs: List[SupportingGR],
) -> Optional[SupportingGR]:
    if not affected_grs:
        return None
    best: Optional[SupportingGR] = None
    best_score = -1.0
    for gr in affected_grs:
        hay = f"{gr.relevance_note or ''} {gr.corpus_excerpt or ''} {gr.label}"
        score = _overlap_score(clause, hay)
        if score > best_score:
            best_score = score
            best = gr
    return best or affected_grs[0]


def build_conflict_pairs(
    finding: ConflictFinding,
    label_map: Dict[str, Dict[str, Any]],
) -> List[ConflictPair]:
    """Pair each conflicting draft clause with corpus-side language."""
    pairs: List[ConflictPair] = []
    clauses = finding.conflicting_clauses or []
    grs = finding.affected_grs or []

    for clause in clauses:
        gr = _find_gr_for_clause(clause, grs)
        if not gr:
            continue

        meta = label_map.get(gr.label, {})
        corpus = (gr.corpus_excerpt or "").strip()
        if not corpus:
            corpus = extract_corpus_excerpt_for_clause(
                clause,
                meta.get("ocr_excerpt") or meta.get("ocr_text") or "",
                meta.get("matched_chunk_text"),
            )

        if not corpus and gr.relevance_note:
            corpus = gr.relevance_note

        pairs.append(
            ConflictPair(
                draft_clause=clause,
                corpus_excerpt=corpus,
                gr_label=gr.label,
                gr_number_canonical=gr.gr_number_canonical or meta.get("gr_number_canonical"),
                relevance_note=gr.relevance_note,
            )
        )

    return pairs


def validate_supporting_grs(
    grs: List[SupportingGR],
    label_map: Dict[str, Dict[str, Any]],
) -> List[SupportingGR]:
    """
    Drop or relabel GR citations that were not present in retrieved context.
    """
    if not grs:
        return []

    valid_labels = set(label_map.keys())
    canonical_to_label: Dict[str, str] = {}
    for lbl, meta in label_map.items():
        canon = meta.get("gr_number_canonical")
        if canon and canon not in canonical_to_label:
            canonical_to_label[str(canon)] = lbl

    cleaned: List[SupportingGR] = []
    seen_labels: set[str] = set()

    for gr in grs:
        label = (gr.label or "").strip()
        canon = (gr.gr_number_canonical or "").strip()

        resolved_label: Optional[str] = None
        if label in valid_labels:
            resolved_label = label
        elif canon and canon in canonical_to_label:
            resolved_label = canonical_to_label[canon]
            print(f"Notice: relabeled hallucinated GR citation {label!r} → {resolved_label!r}")
        else:
            print(
                f"Warning: dropping GR citation not in retrieved context: "
                f"label={label!r} canonical={canon!r}"
            )
            continue

        if resolved_label in seen_labels:
            continue
        seen_labels.add(resolved_label)

        meta = label_map.get(resolved_label, {})
        cleaned.append(
            SupportingGR(
                label=resolved_label,
                gr_number_canonical=canon or meta.get("gr_number_canonical"),
                relevance_note=gr.relevance_note,
                corpus_excerpt=gr.corpus_excerpt,
            )
        )

    return cleaned


def apply_conflict_post_validation(
    finding: ConflictFinding,
    label_map: Dict[str, Dict[str, Any]],
) -> ConflictFinding:
    """Validate citations, enrich corpus excerpts, and build conflict pairs."""
    finding.affected_grs = validate_supporting_grs(finding.affected_grs, label_map)

    # Fill missing corpus_excerpt on each affected GR from OCR
    enriched_grs: List[SupportingGR] = []
    for gr in finding.affected_grs:
        corpus = (gr.corpus_excerpt or "").strip()
        if not corpus:
            meta = label_map.get(gr.label, {})
            clause_seed = (finding.conflicting_clauses or [""])[0]
            corpus = extract_corpus_excerpt_for_clause(
                clause_seed,
                meta.get("ocr_excerpt") or meta.get("ocr_text") or "",
                meta.get("matched_chunk_text"),
            )
        enriched_grs.append(
            SupportingGR(
                label=gr.label,
                gr_number_canonical=gr.gr_number_canonical,
                relevance_note=gr.relevance_note,
                corpus_excerpt=corpus or gr.relevance_note,
            )
        )
    finding.affected_grs = enriched_grs
    finding.conflict_pairs = build_conflict_pairs(finding, label_map)

    if finding.conflicting and not finding.conflicting_clauses and not finding.affected_grs:
        finding.conflicting = False
        finding.confidence = min(finding.confidence, 0.35)
        suffix = " [No validated clause or GR citation — conflict flag cleared.]"
        if suffix not in finding.explanation:
            finding.explanation = (finding.explanation.rstrip() + suffix).strip()

    return finding


def apply_query_post_validation(
    answer: QueryAnswer,
    label_map: Dict[str, Dict[str, Any]],
) -> QueryAnswer:
    answer.supporting_grs = validate_supporting_grs(answer.supporting_grs, label_map)
    return answer


def build_compare_ocr_sections(
    doc_a: Dict[str, Any],
    doc_b: Dict[str, Any],
    gr_id_a: int,
    gr_id_b: int,
    max_ocr_chars: int = COMPARE_OCR_CHARS,
) -> str:
    """Build pairwise comparison context with paragraph-aware OCR excerpts."""
    per_doc = max(1500, max_ocr_chars // 2)

    ocr_a = build_ocr_excerpt_with_context(
        doc_a.get("ocr_text") or "", None, per_doc
    )
    ocr_b = build_ocr_excerpt_with_context(
        doc_b.get("ocr_text") or "", None, per_doc
    )

    return f"""
[GR A]
ID: {gr_id_a}
Canonical GR Number: {doc_a.get('gr_number_canonical')}
Department: {doc_a.get('department')}
Date: {doc_a.get('gr_date')}
Subject: {doc_a.get('subject_mr')}
OCR Excerpt:
{ocr_a if ocr_a else 'No text available'}

============================================================

[GR B]
ID: {gr_id_b}
Canonical GR Number: {doc_b.get('gr_number_canonical')}
Department: {doc_b.get('department')}
Date: {doc_b.get('gr_date')}
Subject: {doc_b.get('subject_mr')}
OCR Excerpt:
{ocr_b if ocr_b else 'No text available'}
""".strip()


def temporal_context_note(results: List[Dict[str, Any]]) -> str:
    """Short note injected into prompts when dates are available."""
    dated = sum(1 for r in results if parse_gr_date(r.get("gr_date")))
    if dated == 0:
        return ""
    return (
        "\nTEMPORAL NOTE: Retrieved GRs are ordered newest-first. "
        "When a newer GR supersedes an older one on the same topic, "
        "treat the newer GR as authoritative and flag supersession explicitly.\n"
    )
