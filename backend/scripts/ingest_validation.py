"""
Post-ingest validation and pipeline readiness checks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Database

STRICT_VALIDATION = os.getenv("STRICT_INGEST_VALIDATION", "false").lower() in (
    "1",
    "true",
    "yes",
)
MIN_OCR_COVERAGE = float(os.getenv("INGEST_MIN_OCR_COVERAGE", "0.5"))
MIN_CANONICAL_COVERAGE = float(os.getenv("INGEST_MIN_CANONICAL_COVERAGE", "0.7"))
MIN_CITATION_RESOLUTION = float(os.getenv("CITATION_MIN_RESOLUTION_RATE", "0.25"))


def _pct(num: int, denom: int) -> float:
    return (100.0 * num / denom) if denom else 0.0


def run_post_ingest_validation(db: Optional[Database] = None) -> Dict[str, Any]:
    """
    Report embedding/graph/citation readiness after ingest.

    Returns a dict of metrics and prints a human-readable summary.
    Exits with code 1 when STRICT_INGEST_VALIDATION=true and thresholds fail.
    """
    owns_db = db is None
    database = db or Database()

    try:
        database.cur.execute("SELECT COUNT(*) FROM gr_documents")
        total = int(database.cur.fetchone()[0])

        database.cur.execute(
            """
            SELECT COUNT(*) FROM gr_documents
            WHERE ocr_text IS NOT NULL AND length(trim(ocr_text)) > 50
            """
        )
        with_ocr = int(database.cur.fetchone()[0])

        database.cur.execute(
            """
            SELECT COUNT(*) FROM gr_documents
            WHERE gr_number_canonical IS NOT NULL AND gr_number_canonical <> ''
            """
        )
        with_canonical = int(database.cur.fetchone()[0])

        database.cur.execute(
            "SELECT COUNT(*) FROM gr_documents WHERE embedding IS NOT NULL"
        )
        embedded = int(database.cur.fetchone()[0])

        chunk_count = database.count_chunks()

        missing_txt = total - with_ocr
        ocr_coverage = _pct(with_ocr, total)
        canonical_coverage = _pct(with_canonical, total)
        embed_coverage = _pct(embedded, total)

        report: Dict[str, Any] = {
            "total_documents": total,
            "with_ocr": with_ocr,
            "missing_ocr": missing_txt,
            "ocr_coverage_pct": round(ocr_coverage, 2),
            "with_canonical_gr": with_canonical,
            "canonical_coverage_pct": round(canonical_coverage, 2),
            "embedded_documents": embedded,
            "embedding_coverage_pct": round(embed_coverage, 2),
            "chunk_count": chunk_count,
            "citation_resolution_pct": None,
            "citation_edges": None,
            "neo4j_ok": None,
            "warnings": [],
            "passed": True,
        }

        if ocr_coverage < MIN_OCR_COVERAGE * 100:
            report["warnings"].append(
                f"Low OCR coverage: {ocr_coverage:.1f}% "
                f"(threshold {MIN_OCR_COVERAGE * 100:.0f}%)"
            )

        if canonical_coverage < MIN_CANONICAL_COVERAGE * 100:
            report["warnings"].append(
                f"Low canonical GR coverage: {canonical_coverage:.1f}% "
                f"(threshold {MIN_CANONICAL_COVERAGE * 100:.0f}%)"
            )

        if embedded == 0 and total > 0:
            report["warnings"].append(
                "No embeddings found — run: python -m embeddings.embed"
            )

        if chunk_count == 0 and total > 0:
            report["warnings"].append(
                "No chunk embeddings found — run: python -m embeddings.embed"
            )

        # Citation resolution sample (full corpus scan)
        try:
            from graph.reference_resolver import ReferenceResolver

            resolver = ReferenceResolver(db=database)
            pairs = resolver.resolve_all()
            rate = resolver.resolution_rate()
            report["citation_resolution_pct"] = round(rate, 2)
            report["citation_edges"] = len(pairs)
            if rate < MIN_CITATION_RESOLUTION * 100:
                report["warnings"].append(
                    f"Low citation resolution: {rate:.1f}% "
                    f"(threshold {MIN_CITATION_RESOLUTION * 100:.0f}%)"
                )
            resolver.close()
        except Exception as e:
            report["warnings"].append(f"Citation resolution check failed: {e}")

        # Neo4j connectivity (optional)
        try:
            from graph.neo4j_query import check_neo4j_health

            neo = check_neo4j_health()
            report["neo4j_ok"] = neo.get("ok", False)
            if not report["neo4j_ok"]:
                report["warnings"].append(
                    f"Neo4j unavailable: {neo.get('error') or 'unknown'}"
                )
        except Exception as e:
            report["neo4j_ok"] = False
            report["warnings"].append(f"Neo4j health check failed: {e}")

        report["passed"] = len(report["warnings"]) == 0

        print("\n========== POST-INGEST VALIDATION ==========")
        print(f"Documents          : {total}")
        print(f"OCR coverage       : {with_ocr}/{total} ({ocr_coverage:.1f}%)")
        print(f"Canonical GR       : {with_canonical}/{total} ({canonical_coverage:.1f}%)")
        print(f"Embeddings         : {embedded}/{total} ({embed_coverage:.1f}%)")
        print(f"Chunks             : {chunk_count}")
        if report["citation_resolution_pct"] is not None:
            print(
                f"Citation resolution: {report['citation_resolution_pct']:.1f}% "
                f"({report['citation_edges']} edges)"
            )
        print(f"Neo4j              : {'ok' if report['neo4j_ok'] else 'unavailable'}")
        if report["warnings"]:
            print("\nWarnings:")
            for w in report["warnings"]:
                print(f"  - {w}")
        else:
            print("\nAll readiness checks passed.")
        print("============================================\n")

        if STRICT_VALIDATION and report["warnings"]:
            raise SystemExit(
                "Ingest validation failed (STRICT_INGEST_VALIDATION=true). "
                "See warnings above."
            )

        return report

    finally:
        if owns_db:
            database.close()
