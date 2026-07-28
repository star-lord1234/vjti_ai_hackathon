"""
Deterministic citation → document resolution (no LLM).

Reads citations from PostgreSQL, extracts / normalizes GR numbers,
and matches them to gr_documents.gr_number_canonical.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.normalize import canonical_gr_number, normalize_gr_number
from database.db import Database

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GR number extraction from citation "raw" text
# ---------------------------------------------------------------------------

# Stop capturing when these labels appear (date / trailing prose)
_STOP_LOOKAHEAD = (
    r"(?=\s*(?:"
    r"दि\.|दिनांक|दिनाक|Date|"
    r"समक्रमांक|चे पत्र|अन्वये|$|,))"
)

_LABELLED_GR = re.compile(
    r"(?:क्रमांक|कमांक|क्र\.?)\s*[.:ः\-–—]*\s*"
    r"(.+?)"
    + _STOP_LOOKAHEAD,
    re.UNICODE,
)

# Structural fallback: CODE-YEAR/(...)/SECTION  (common Maharashtra GR shape)
_STRUCTURAL_GR = re.compile(
    r"("
    r"[A-Za-z\u0900-\u097F][A-Za-z0-9\u0900-\u097F\s\.]{0,40}?"
    r"-\s*[०१२३४५६७८९0-9]{4}\s*"
    r"/\s*\([^)]{1,40}\)\s*"
    r"/\s*[A-Za-z0-9\u0900-\u097F\-]{1,40}"
    r")",
    re.UNICODE,
)


def extract_gr_number_from_citation(raw_text: str) -> Optional[str]:
    """
    Pull a GR identifier out of a citation string.
    Returns the raw extracted token (not yet normalised), or None.
    """

    if not raw_text or not str(raw_text).strip():
        return None

    text = str(raw_text).strip()

    # Prefer explicit क्र / क्रमांक label
    match = _LABELLED_GR.search(text)
    if match:
        candidate = match.group(1).strip(" \t.:ः-–—")
        candidate = _trim_citation_noise(candidate)
        if _looks_like_gr(candidate):
            return candidate

    # Fallback: structural pattern anywhere in the string
    match = _STRUCTURAL_GR.search(text)
    if match:
        candidate = _trim_citation_noise(match.group(1))
        if _looks_like_gr(candidate):
            return candidate

    return None


def _trim_citation_noise(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    # Drop leading department prose before the actual code if still glued
    # e.g. "उच्च व तंत्रशिक्षण विभाग बैठक -9002/..." → keep from last token with year
    value = value.strip(" ,;.-")
    return value


def _looks_like_gr(value: str) -> bool:
    if not value or len(value) < 5:
        return False
    # Must contain a 4-digit year (EN or Marathi) OR a slash-heavy file code
    if not re.search(r"[०१२३४५६७८९0-9]{4}", value):
        return False
    # Reject pure dates / gazette ordinance noise without dept-like token
    if re.fullmatch(r"[०१२३४५६७८९0-9./\-\s]+", value):
        return False
    return True


class ReferenceResolver:
    """
    Resolve citation text to existing gr_documents rows via canonical GR.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self._owns_db = db is None

        # canonical -> document id (lowest id wins)
        self.canonical_index: Dict[str, int] = self.db.build_canonical_index()

        self.stats = {
            "documents_processed": 0,
            "references_found": 0,
            "references_resolved": 0,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_reference(self, raw_text: str) -> Optional[Dict[str, Any]]:
        """
        Resolve a single citation string.

        Returns
        -------
        dict with keys: target_id, gr_number, gr_number_normalized,
        gr_number_canonical, raw
        or None if no GR could be extracted / no DB match.
        """

        extracted = extract_gr_number_from_citation(raw_text)
        if not extracted:
            return None

        normalized = normalize_gr_number(extracted)
        canonical = canonical_gr_number(extracted)
        if not canonical:
            return None

        target_id = self.canonical_index.get(canonical)
        if target_id is None:
            return None

        return {
            "target_id": target_id,
            "gr_number": extracted,
            "gr_number_normalized": normalized,
            "gr_number_canonical": canonical,
            "raw": raw_text,
        }

    def resolve_document(self, document: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Resolve all citations on one document.

        document must include: id, citations (list of {raw, date?} or strings)

        Returns list of
        {source_id, target_id, raw, gr_number_canonical?}
        """

        source_id = document["id"]
        citations = document.get("citations") or []

        resolved: List[Dict[str, Any]] = []

        for cite in citations:
            self.stats["references_found"] += 1

            if isinstance(cite, str):
                raw = cite
            elif isinstance(cite, dict):
                raw = cite.get("raw") or ""
            else:
                continue

            if not raw:
                continue

            hit = self.resolve_reference(raw)
            if hit is None:
                continue

            target_id = hit["target_id"]
            if target_id == source_id:
                # Skip self-loops
                continue

            self.stats["references_resolved"] += 1
            resolved.append(
                {
                    "source_id": source_id,
                    "target_id": target_id,
                    "raw": raw,
                    "gr_number": hit["gr_number"],
                    "gr_number_canonical": hit["gr_number_canonical"],
                }
            )

        self.stats["documents_processed"] += 1
        return resolved

    def resolve_all(self) -> List[Tuple[int, int]]:
        """
        Resolve citations for every document.

        Returns
        -------
        list of unique (source_id, target_id) pairs suitable for Neo4j import.
        """

        self.stats = {
            "documents_processed": 0,
            "references_found": 0,
            "references_resolved": 0,
        }

        documents = self.db.get_documents_for_resolution()
        pairs: List[Tuple[int, int]] = []
        seen = set()

        for doc in documents:
            for ref in self.resolve_document(doc):
                pair = (ref["source_id"], ref["target_id"])
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)

        self._log_stats(len(pairs))
        return pairs

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_stats(self, unique_pairs: int) -> None:
        found = self.stats["references_found"]
        resolved = self.stats["references_resolved"]
        rate = (100.0 * resolved / found) if found else 0.0

        logger.info("Documents processed : %s", self.stats["documents_processed"])
        logger.info("References found    : %s", found)
        logger.info("References resolved : %s", resolved)
        logger.info("Resolution rate     : %.2f%%", rate)
        logger.info("Unique edges        : %s", unique_pairs)

        # Also print for CLI convenience
        print("========== Citation resolution ==========")
        print(f"Documents processed : {self.stats['documents_processed']}")
        print(f"References found    : {found}")
        print(f"References resolved : {resolved}")
        print(f"Resolution rate     : {rate:.2f}%")
        print(f"Unique edges        : {unique_pairs}")
        print("=========================================")

    def close(self) -> None:
        if self._owns_db:
            self.db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    resolver = ReferenceResolver()
    try:
        pairs = resolver.resolve_all()
        print(f"Sample edges: {pairs[:10]}")
    finally:
        resolver.close()


if __name__ == "__main__":
    main()
