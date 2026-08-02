#!/usr/bin/env python3
"""
Golden retrieval evaluation — recall@k and MRR against labeled query cases.

Usage:
  python scripts/eval_retrieval.py
  python scripts/eval_retrieval.py --min-mrr 0.25 --fail-on-miss
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = SCRIPT_DIR.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from embeddings.search import semantic_search, build_draft_query_segments
from retrieval.hybrid import hybrid_search

GOLDEN_FILE = SCRIPT_DIR / "fixtures" / "golden_retrieval.json"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"


def _normalize(text: str) -> str:
    return (text or "").lower()


def _result_matches(
    row: Dict[str, Any],
    *,
    subject_keywords: List[str],
    department_keywords: List[str],
    canonical_substrings: List[str],
) -> bool:
    subject = _normalize(str(row.get("subject_mr") or ""))
    dept = _normalize(str(row.get("department") or ""))
    canon = _normalize(str(row.get("gr_number_canonical") or ""))

    if canonical_substrings:
        if any(sub.lower() in canon for sub in canonical_substrings):
            return True

    if subject_keywords:
        if any(kw.lower() in subject for kw in subject_keywords):
            return True

    if department_keywords:
        if any(kw.lower() in dept for kw in department_keywords):
            return True

    return not (subject_keywords or department_keywords or canonical_substrings)


def _load_query(case: Dict[str, Any]) -> str:
    if case.get("query_text"):
        return str(case["query_text"]).strip()
    query_file = case.get("query_file")
    if query_file:
        path = FIXTURES_DIR / query_file
        return path.read_text(encoding="utf-8").strip()
    raise ValueError(f"Case {case.get('id')} has no query_text or query_file")


def evaluate_case(case: Dict[str, Any], *, use_hybrid: bool) -> Dict[str, Any]:
    query = _load_query(case)
    top_k = int(case.get("top_k", 10))
    subject_kw = list(case.get("expected_subject_keywords") or [])
    dept_kw = list(case.get("expected_department_keywords") or [])
    canon_sub = list(case.get("expected_canonical_substrings") or [])
    min_recall = int(case.get("min_recall_at_k", 1))

    if use_hybrid:
        segments = build_draft_query_segments(query)
        results, _meta = hybrid_search(
            segments if len(segments) > 1 else query,
            top_k=top_k,
            hops=0,
            return_meta=True,
        )
    else:
        results = semantic_search(query, top_k=top_k)

    hits_at_k = 0
    reciprocal_rank: Optional[float] = None

    for rank, row in enumerate(results[:top_k], start=1):
        if _result_matches(
            row,
            subject_keywords=subject_kw,
            department_keywords=dept_kw,
            canonical_substrings=canon_sub,
        ):
            hits_at_k += 1
            if reciprocal_rank is None:
                reciprocal_rank = 1.0 / rank

    passed = hits_at_k >= min_recall
    return {
        "id": case.get("id"),
        "query_chars": len(query),
        "retrieved": len(results),
        "hits_at_k": hits_at_k,
        "min_recall_at_k": min_recall,
        "reciprocal_rank": reciprocal_rank or 0.0,
        "passed": passed,
        "top_ids": [r.get("id") for r in results[:5]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate retrieval against golden set")
    parser.add_argument(
        "--golden",
        type=Path,
        default=GOLDEN_FILE,
        help="Path to golden_retrieval.json",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Use hybrid_search (vector-only, hops=0) instead of semantic_search",
    )
    parser.add_argument(
        "--min-mrr",
        type=float,
        default=0.0,
        help="Fail if mean reciprocal rank is below this value",
    )
    parser.add_argument(
        "--fail-on-miss",
        action="store_true",
        help="Exit 1 if any case fails min_recall_at_k",
    )
    args = parser.parse_args()

    if not args.golden.exists():
        print(f"[ERROR] Golden file not found: {args.golden}")
        return 1

    payload = json.loads(args.golden.read_text(encoding="utf-8"))
    cases = payload.get("cases") or []
    if not cases:
        print("[ERROR] No cases in golden retrieval file")
        return 1

    print("=" * 72)
    print("GOLDEN RETRIEVAL EVALUATION")
    print(f"Cases: {len(cases)} | Mode: {'hybrid(hops=0)' if args.hybrid else 'semantic'}")
    print("=" * 72)

    results: List[Dict[str, Any]] = []
    for case in cases:
        try:
            outcome = evaluate_case(case, use_hybrid=args.hybrid)
        except Exception as exc:
            print(f"[FAIL] {case.get('id')}: {exc}")
            if args.fail_on_miss:
                return 1
            continue

        results.append(outcome)
        status = "PASS" if outcome["passed"] else "FAIL"
        print(
            f"{outcome['id']:<28} | hits@{case.get('top_k', 10)}={outcome['hits_at_k']:<2} "
            f"| MRR={outcome['reciprocal_rank']:.3f} | {status}"
        )

    if not results:
        print("[ERROR] No cases evaluated successfully")
        return 1

    mrr = sum(r["reciprocal_rank"] for r in results) / len(results)
    recall_pass = sum(1 for r in results if r["passed"])
    print("-" * 72)
    print(f"Recall pass rate: {recall_pass}/{len(results)}")
    print(f"Mean reciprocal rank (MRR): {mrr:.3f}")

    failed = [r for r in results if not r["passed"]]
    if args.fail_on_miss and failed:
        print(f"\n>>> {len(failed)} CASE(S) BELOW min_recall_at_k <<<")
        return 1

    if args.min_mrr > 0 and mrr < args.min_mrr:
        print(f"\n>>> MRR {mrr:.3f} below threshold {args.min_mrr:.3f} <<<")
        return 1

    print("\n>>> GOLDEN RETRIEVAL EVALUATION COMPLETE <<<\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
