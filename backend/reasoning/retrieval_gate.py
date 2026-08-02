"""
Pre-LLM retrieval quality assessment and lightweight reranking.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Set

from embeddings.search import get_min_score
from retrieval.models import HybridSearchMeta

MIN_RESULTS = int(os.getenv("RETRIEVAL_MIN_RESULTS", "1"))
RERANK_KEYWORD_BOOST = float(os.getenv("RETRIEVAL_KEYWORD_BOOST", "0.05"))


def _tokenize(text: str) -> Set[str]:
    return {
        t
        for t in re.split(r"\W+", (text or "").lower())
        if len(t) >= 4
    }


def rerank_with_draft_overlap(
    results: List[Dict[str, Any]],
    draft_text: str,
    draft_keywords: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
  Lightweight reranker: boost vector scores when draft tokens overlap
  subject/department/matched chunk text (no cross-encoder required).
    """
    if not results or not draft_text.strip():
        return results

    draft_tokens = draft_keywords or _tokenize(draft_text)
    if not draft_tokens:
        return results

    reranked: List[Dict[str, Any]] = []
    for row in results:
        haystack = " ".join(
            str(row.get(k) or "")
            for k in (
                "subject_mr",
                "department",
                "matched_chunk_text",
                "gr_number_canonical",
            )
        )
        doc_tokens = _tokenize(haystack)
        overlap = len(draft_tokens & doc_tokens)
        base = float(row.get("score") or 0.0)
        boosted = base + overlap * RERANK_KEYWORD_BOOST
        updated = dict(row)
        updated["score"] = boosted
        updated["rerank_boost"] = round(boosted - base, 4)
        reranked.append(updated)

    return sorted(reranked, key=lambda r: -(r.get("score") or 0.0))


def assess_retrieval_quality(
    results: List[Dict[str, Any]],
    meta: Optional[HybridSearchMeta] = None,
    *,
    min_score: Optional[float] = None,
    min_results: int = MIN_RESULTS,
) -> Dict[str, Any]:
    """
    Evaluate whether retrieval is sufficient to proceed to LLM reasoning.
    Returns a dict suitable for RetrievalQualityInfo serialization.
    """
    threshold = min_score if min_score is not None else get_min_score()
    warnings: List[str] = []

    scores = [float(r.get("score") or 0.0) for r in results]
    above = [s for s in scores if s >= threshold]
    chunk_hits = sum(1 for r in results if r.get("matched_chunk_text"))

    if not results:
        warnings.append("No GRs retrieved above similarity threshold.")
    elif len(above) < min_results:
        warnings.append(
            f"Only {len(above)} result(s) at or above score {threshold:.2f} "
            f"(need {min_results})."
        )

    if chunk_hits == 0 and results:
        warnings.append("No clause-level chunk matches — document-level fallback only.")

    if meta:
        if meta.graph_degraded:
            warnings.append(
                f"Neo4j graph degraded: {meta.graph_error or 'unknown error'}."
            )
        if meta.graph_skipped:
            warnings.append("Graph expansion skipped (vector-only retrieval).")
        if meta.vector_seeds == 0:
            warnings.append("Vector search returned zero seed documents.")

    max_score = max(scores) if scores else 0.0
    passed = bool(results) and len(above) >= min_results

    return {
        "passed": passed,
        "result_count": len(results),
        "above_threshold_count": len(above),
        "max_score": round(max_score, 4),
        "min_score_threshold": threshold,
        "chunk_hits": chunk_hits,
        "graph_degraded": bool(meta and meta.graph_degraded),
        "graph_skipped": bool(meta and meta.graph_skipped),
        "warnings": warnings,
    }


def build_degradation_reasons(
    quality: Dict[str, Any],
    store_sync: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Merge retrieval and store-sync warnings into client-visible reasons."""
    reasons = list(quality.get("warnings") or [])
    if store_sync and not store_sync.get("in_sync", True):
        reasons.extend(store_sync.get("warnings") or [])
    # Deduplicate preserving order
    seen: Set[str] = set()
    out: List[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out
