"""
Context builder for RAG prompt construction from hybrid search results.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Database
from reasoning.prompt_utils import (
    build_ocr_excerpt_with_context,
    parse_gr_date,
    sort_results_by_recency,
)

DEFAULT_MAX_FULL_TEXT = int(os.getenv("REASONING_MAX_FULL_TEXT_DOCS", "8"))
DEFAULT_EXCERPT_CHARS = int(os.getenv("REASONING_EXCERPT_CHARS", "1500"))
MAX_TOTAL_CONTEXT_CHARS = int(os.getenv("REASONING_MAX_CONTEXT_CHARS", "16000"))
GRAPH_OCR_MIN_SLOTS = int(os.getenv("GRAPH_OCR_MIN_SLOTS", "2"))
GRAPH_OCR_SLOT_RATIO = float(os.getenv("GRAPH_OCR_SLOT_RATIO", "0.3"))
MIN_ENTRY_CHARS = 120  # minimum chars for a metadata-only stub entry


def _select_ocr_document_ids(
    results: List[Dict[str, Any]],
    max_full_text: int,
) -> Set[int]:
    """
    Choose which document IDs receive OCR excerpts in the LLM context.
    """
    if max_full_text <= 0:
        return set()

    vector_hits = [r for r in results if r.get("source") == "vector" and "id" in r]
    graph_hits = [r for r in results if r.get("source") == "graph" and "id" in r]

    graph_slots = min(
        max_full_text,
        max(GRAPH_OCR_MIN_SLOTS, int(max_full_text * GRAPH_OCR_SLOT_RATIO)),
    )
    vector_slots = max(0, max_full_text - graph_slots)

    graph_sorted = sorted(graph_hits, key=lambda r: (r.get("hop_distance") or 99, r["id"]))
    vector_sorted = sorted(
        vector_hits, key=lambda r: (-(r.get("score") or 0.0), r["id"])
    )

    ocr_ids: Set[int] = set()
    for r in graph_sorted[:graph_slots]:
        ocr_ids.add(r["id"])
    for r in vector_sorted[:vector_slots]:
        ocr_ids.add(r["id"])

    if len(ocr_ids) < max_full_text:
        remaining = max_full_text - len(ocr_ids)
        combined = sorted(
            results,
            key=lambda r: (
                0 if r.get("source") == "graph" else 1,
                r.get("hop_distance") or 0,
                -(r.get("score") or 0.0),
            ),
        )
        for r in combined:
            if "id" not in r:
                continue
            if r["id"] not in ocr_ids:
                ocr_ids.add(r["id"])
                remaining -= 1
                if remaining <= 0:
                    break

    return ocr_ids


def _build_entry_text(
    res: Dict[str, Any],
    label: str,
    ocr_map: Dict[int, str],
    target_ocr_ids: Set[int],
    excerpt_chars: int,
) -> str:
    doc_id = res.get("id")
    gr_num = res.get("gr_number_canonical") or "Unknown"
    dept = res.get("department") or "Unknown"
    gr_date = str(res.get("gr_date")) if res.get("gr_date") else "Unknown"
    subject = res.get("subject_mr") or "Unknown"
    source = res.get("source") or "unknown"
    hops = res.get("hop_distance") if res.get("hop_distance") is not None else 0
    score = f"{res['score']:.4f}" if res.get("score") is not None else "N/A"

    d = parse_gr_date(res.get("gr_date"))
    date_note = f" ({d.isoformat()})" if d else ""

    entry_lines = [
        f"{label}",
        f"ID: {doc_id}",
        f"GR Number: {gr_num}",
        f"Department: {dept}",
        f"Date: {gr_date}{date_note}",
        f"Subject: {subject}",
        f"Retrieval Source: {source} (Hop Distance: {hops}, Score: {score})",
    ]

    matched = (res.get("matched_chunk_text") or "").strip()
    full_ocr = ocr_map.get(doc_id, "") if doc_id in ocr_map else ""

    if doc_id in target_ocr_ids or matched:
        excerpt = build_ocr_excerpt_with_context(
            full_ocr, matched or None, excerpt_chars
        )
        if excerpt:
            entry_lines.append(f"OCR Excerpt:\n{excerpt}")
        else:
            entry_lines.append("OCR Excerpt: [not available]")
    else:
        entry_lines.append("OCR Excerpt: [metadata only — not in full-text budget]")

    return "\n".join(entry_lines)


def _fit_entries_to_budget(
    entries: List[str],
    max_chars: int,
) -> List[str]:
    """
    Fit all GR entries into the context budget by shrinking excerpts before dropping GRs.
    """
    if not entries:
        return []

    total = sum(len(e) for e in entries) + max(0, len(entries) - 1) * 2
    if total <= max_chars:
        return entries

    # Pass 1: compress OCR sections by removing duplicate truncation markers
    # Pass 2: replace long OCR blocks with shorter stubs for tail entries
    selected: List[str] = []
    current = 0
    separator = "\n\n"

    for i, entry in enumerate(entries):
        if current + len(entry) <= max_chars:
            selected.append(entry)
            current += len(entry) + len(separator)
            continue

        remaining_slots = len(entries) - i
        remaining_budget = max_chars - current
        if remaining_budget < MIN_ENTRY_CHARS * remaining_slots:
            # Compress this and remaining to metadata stubs
            stub = _metadata_stub_from_entry(entry)
            if current + len(stub) <= max_chars:
                selected.append(stub)
                current += len(stub) + len(separator)
            break

        # Truncate OCR portion of this entry to fit remaining share
        share = max(MIN_ENTRY_CHARS, remaining_budget // remaining_slots)
        compressed = _compress_entry(entry, share)
        selected.append(compressed)
        current += len(compressed) + len(separator)

    return selected


def _metadata_stub_from_entry(entry: str) -> str:
    """Keep label + key metadata lines only."""
    lines = entry.split("\n")
    keep = []
    for line in lines:
        if line.startswith("OCR Excerpt"):
            break
        keep.append(line)
    keep.append("OCR Excerpt: [omitted — context budget]")
    return "\n".join(keep)


def _compress_entry(entry: str, max_len: int) -> str:
    if len(entry) <= max_len:
        return entry
    ocr_idx = entry.find("OCR Excerpt:")
    if ocr_idx == -1:
        return entry[: max_len - 20] + "\n... [truncated]"
    header = entry[:ocr_idx].rstrip()
    budget = max(80, max_len - len(header) - 30)
    ocr_body = entry[ocr_idx + len("OCR Excerpt:") :].strip()
    short_ocr = ocr_body[:budget]
    if len(ocr_body) > budget:
        short_ocr += " ... [truncated]"
    return f"{header}\nOCR Excerpt:\n{short_ocr}"


def build_context_block(
    results: List[Dict[str, Any]],
    full_text_ids: Optional[List[int]] = None,
    max_full_text: int = DEFAULT_MAX_FULL_TEXT,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
    db: Optional[Database] = None,
    sort_by_date: bool = True,
    max_context_chars: Optional[int] = None,
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """
    Construct formatted context block from hybrid search results.

    Results are ordered newest-first by default for supersession-aware reasoning.
    """
    if not results:
        return "No related Government Resolutions found.", {}

    ordered = sort_results_by_recency(results) if sort_by_date else list(results)

    if full_text_ids is not None:
        target_ocr_ids = set(full_text_ids)
    else:
        target_ocr_ids = _select_ocr_document_ids(ordered, max_full_text)

    ocr_map: Dict[int, str] = {}
    if target_ocr_ids:
        owns_db = db is None
        database = db or Database()
        try:
            query = "SELECT id, ocr_text FROM gr_documents WHERE id = ANY(%s)"
            database.cur.execute(query, (list(target_ocr_ids),))
            for doc_id, text in database.cur.fetchall():
                if text:
                    ocr_map[doc_id] = str(text)
        finally:
            if owns_db:
                database.close()

    entries: List[str] = []
    label_map: Dict[str, Dict[str, Any]] = {}

    for idx, res in enumerate(ordered, 1):
        label = f"[GR {idx}]"
        doc_id = res.get("id")

        label_map[label] = {
            "id": doc_id,
            "filename": res.get("filename"),
            "gr_number_canonical": res.get("gr_number_canonical"),
            "department": res.get("department"),
            "gr_date": str(res.get("gr_date")) if res.get("gr_date") else None,
            "subject_mr": res.get("subject_mr"),
            "matched_chunk_text": res.get("matched_chunk_text"),
            "ocr_excerpt": build_ocr_excerpt_with_context(
                ocr_map.get(doc_id, "") if doc_id in ocr_map else "",
                res.get("matched_chunk_text"),
                excerpt_chars,
            )
            if doc_id in target_ocr_ids or res.get("matched_chunk_text")
            else "",
            "ocr_text": ocr_map.get(doc_id, "") if doc_id in ocr_map else "",
        }

        entries.append(
            _build_entry_text(res, label, ocr_map, target_ocr_ids, excerpt_chars)
        )

    context_budget = max_context_chars if max_context_chars is not None else MAX_TOTAL_CONTEXT_CHARS
    selected_entries = _fit_entries_to_budget(entries, context_budget)

    if len(selected_entries) < len(entries):
        print(
            f"Notice: context budget compressed {len(entries)} GR entries "
            f"to {len(selected_entries)} (max {context_budget} chars)."
        )

    context_text = "\n\n" + ("=" * 60) + "\n\n" + "\n\n".join(selected_entries)
    return context_text, label_map
