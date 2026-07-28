"""
Context builder for RAG prompt construction from hybrid search results.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Database

DEFAULT_MAX_FULL_TEXT = int(os.getenv("REASONING_MAX_FULL_TEXT_DOCS", "4"))
DEFAULT_EXCERPT_CHARS = 600
MAX_TOTAL_CONTEXT_CHARS = 8000


def build_context_block(
    results: List[Dict[str, Any]],
    full_text_ids: Optional[List[int]] = None,
    max_full_text: int = DEFAULT_MAX_FULL_TEXT,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
    db: Optional[Database] = None,
) -> Tuple[str, Dict[str, Dict[str, Any]]]:
    """
    Construct formatted context block from hybrid search results.

    Parameters
    ----------
    results : list[dict]
        Output from retrieval.hybrid.hybrid_search().
    full_text_ids : list[int], optional
        Explicit list of document IDs to fetch OCR text for.
    max_full_text : int, default 8
        Maximum number of documents to include OCR text excerpts for.
    excerpt_chars : int, default 1200
        Maximum characters per OCR excerpt.
    db : Database, optional
        Database connection instance.

    Returns
    -------
    tuple[str, dict]
        (context_text, label_map) where label_map maps "[GR N]" -> doc details.
    """
    if not results:
        return "No related Government Resolutions found.", {}

    # Determine which documents get OCR excerpts
    if full_text_ids is not None:
        target_ocr_ids = set(full_text_ids)
    else:
        # Prioritize vector hits first (highest score), then lowest hop_distance
        prioritized = sorted(
            results,
            key=lambda r: (
                0 if r.get("source") == "vector" else 1,
                -(r.get("score") or 0.0),
                r.get("hop_distance") or 0,
            ),
        )
        target_ocr_ids = {r["id"] for r in prioritized[:max_full_text] if "id" in r}

    # Fetch OCR text for target IDs from PostgreSQL
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

    # Format context entries and build label mapping
    entries = []
    label_map: Dict[str, Dict[str, Any]] = {}

    for idx, res in enumerate(results, 1):
        label = f"[GR {idx}]"
        doc_id = res.get("id")
        gr_num = res.get("gr_number_canonical") or "Unknown"
        dept = res.get("department") or "Unknown"
        gr_date = str(res.get("gr_date")) if res.get("gr_date") else "Unknown"
        subject = res.get("subject_mr") or "Unknown"
        source = res.get("source") or "unknown"
        hops = res.get("hop_distance") if res.get("hop_distance") is not None else 0
        score = f"{res['score']:.4f}" if res.get("score") is not None else "N/A"

        label_map[label] = {
            "id": doc_id,
            "filename": res.get("filename"),
            "gr_number_canonical": gr_num,
            "department": dept,
            "gr_date": gr_date,
            "subject_mr": subject,
        }

        entry_lines = [
            f"{label}",
            f"ID: {doc_id}",
            f"GR Number: {gr_num}",
            f"Department: {dept}",
            f"Date: {gr_date}",
            f"Subject: {subject}",
            f"Retrieval Source: {source} (Hop Distance: {hops}, Score: {score})",
        ]

        if doc_id in ocr_map:
            raw_ocr = ocr_map[doc_id].strip()
            truncated_ocr = raw_ocr[:excerpt_chars]
            if len(raw_ocr) > excerpt_chars:
                truncated_ocr += " ... [truncated]"
            entry_lines.append(f"OCR Excerpt:\n{truncated_ocr}")

        entries.append("\n".join(entry_lines))

    # Assemble entries respecting MAX_TOTAL_CONTEXT_CHARS budget
    selected_entries = []
    current_length = 0

    for entry in entries:
        if current_length + len(entry) > MAX_TOTAL_CONTEXT_CHARS and selected_entries:
            break
        selected_entries.append(entry)
        current_length += len(entry)

    context_text = "\n\n" + ("=" * 60) + "\n\n" + "\n\n".join(selected_entries)
    return context_text, label_map

