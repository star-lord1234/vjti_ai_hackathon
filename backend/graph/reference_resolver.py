"""
Deterministic citation → document resolution (no LLM).

Reads citations from PostgreSQL, extracts / normalizes GR numbers,
and matches them to gr_documents.gr_number_canonical.
"""

from __future__ import annotations

import logging
import re
import sys
import os
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

# English "No." / "Number" prefix (common in bilingual citations)
_ENGLISH_NO = re.compile(
    r"(?:No\.?|Number|Ref\.?)\s*[:\-]?\s*"
    r"([A-Za-z0-9\u0900-\u097F][\w\u0900-\u097F\s\./\-]{4,100})"
    + _STOP_LOOKAHEAD,
    re.IGNORECASE | re.UNICODE,
)

# शासन निर्णय क्र. variant
_GOV_ORDER_NO = re.compile(
    r"शासन\s+निर्णय\s+क्र[\s\.:ः\-–—]*\s*"
    r"(.+?)"
    + _STOP_LOOKAHEAD,
    re.UNICODE,
)

# Letter reference: पत्र क्रमांक
_LETTER_NO = re.compile(
    r"पत्र\s+क्र[\s\.:ः\-–—]*\s*"
    r"(.+?)"
    + _STOP_LOOKAHEAD,
    re.UNICODE,
)

# प्र.क्र. / प्रक्र inline file reference
_PROKRI_LABEL = re.compile(
    r"प्र\.?\s*क्र\.?\s*[:\-]?\s*"
    r"(.+?)"
    + _STOP_LOOKAHEAD,
    re.UNICODE,
)

# शासन शुध्दीपत्रक / परिपत्रक क्र.
_DOC_TYPE_NO = re.compile(
    r"शासन\s+(?:निर्णय|शुध्दीपत्रक|परिपत्रक|पत्र)\s+क्र[\s\.:ः\-–—]*\s*"
    r"(.+?)"
    + _STOP_LOOKAHEAD,
    re.UNICODE,
)

# Loose structural: dept-YEAR/middle/section without strict parens
_STRUCTURAL_GR_LOOSE = re.compile(
    r"("
    r"[\w\u0900-\u097F][\w\u0900-\u097F\s\.\-]{0,35}"
    r"-\s*[०१२३४५६७८९0-9]{4}\s*"
    r"/\s*[^,;]+?"
    r"/\s*[\w\u0900-\u097F\-]+"
    r")",
    re.UNICODE,
)

DEFAULT_MIN_RESOLUTION_RATE = float(os.getenv("CITATION_MIN_RESOLUTION_RATE", "0.25"))
CI_MIN_RESOLUTION_RATE = float(os.getenv("CITATION_CI_MIN_RESOLUTION_RATE", "0.50"))


class CitationResolutionError(RuntimeError):
    """Raised when citation resolution rate falls below a required threshold."""


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

    for pattern in (_GOV_ORDER_NO, _LETTER_NO, _DOC_TYPE_NO, _PROKRI_LABEL, _ENGLISH_NO):
        match = pattern.search(text)
        if match:
            candidate = _trim_citation_noise(match.group(1))
            if _looks_like_gr(candidate):
                return candidate

    # Fallback: structural patterns
    for pattern in (_STRUCTURAL_GR, _STRUCTURAL_GR_LOOSE):
        match = pattern.search(text)
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

        # canonical -> document id (lowest id wins; duplicates tracked)
        index, self.duplicate_canonicals = self.db.build_canonical_index()
        self.canonical_index = index

        if self.duplicate_canonicals:
            logger.warning(
                "Found %d duplicate gr_number_canonical values (lowest id kept): %s",
                len(self.duplicate_canonicals),
                self.duplicate_canonicals[:5],
            )
            print(
                f"Warning: {len(self.duplicate_canonicals)} duplicate canonical GR numbers "
                f"in database (lowest id kept for each)."
            )

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
        self.check_resolution_quality()
        return pairs

    def resolution_rate(self) -> float:
        found = self.stats["references_found"]
        resolved = self.stats["references_resolved"]
        return (100.0 * resolved / found) if found else 0.0

    def check_resolution_quality(
        self, min_rate: float = DEFAULT_MIN_RESOLUTION_RATE
    ) -> float:
        """
        Log a warning if citation resolution rate falls below the threshold.
        Returns the resolution rate (0–100).
        """
        rate = self.resolution_rate()
        if self.stats["references_found"] == 0:
            logger.warning("No citations found in corpus for graph edge resolution.")
            print("Warning: No citations found in corpus — graph will have no CITES edges.")
            return rate

        if rate < min_rate * 100:
            msg = (
                f"Citation resolution rate {rate:.1f}% is below threshold "
                f"({min_rate * 100:.0f}%). Graph expansion quality may be poor."
            )
            logger.warning(msg)
            print(f"Warning: {msg}")

        return rate

    def enforce_resolution_quality(
        self,
        min_rate: float = CI_MIN_RESOLUTION_RATE,
        *,
        require_citations: bool = True,
    ) -> float:
        """
        Assert citation resolution meets *min_rate* (0–1 fraction).
        Raises CitationResolutionError when below threshold — for CI / strict ingest.
        """
        rate = self.resolution_rate()
        found = self.stats["references_found"]

        if require_citations and found == 0:
            raise CitationResolutionError(
                "No citations found in corpus for graph edge resolution."
            )

        if found > 0 and rate < min_rate * 100:
            raise CitationResolutionError(
                f"Citation resolution rate {rate:.1f}% is below required "
                f"threshold ({min_rate * 100:.0f}%)."
            )

        return rate

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
