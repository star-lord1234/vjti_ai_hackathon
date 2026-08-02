#!/usr/bin/env python3
"""CLI gate for Postgres ↔ Neo4j store sync."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.sync_status import check_store_sync


def main() -> int:
    report = check_store_sync()
    print("========== STORE SYNC CHECK ==========")
    print(f"Postgres documents : {report['postgres_documents']}")
    print(f"Neo4j GR nodes     : {report.get('neo4j_gr_nodes')}")
    print(f"Neo4j CITES edges  : {report.get('neo4j_cites_edges')}")
    print(f"Chunk embeddings   : {report.get('chunk_count')}")
    print(f"OCR w/o embedding  : {report.get('ocr_without_embedding')}")
    print(f"In sync            : {report['in_sync']}")
    if report.get("warnings"):
        print("\nWarnings:")
        for w in report["warnings"]:
            print(f"  - {w}")
    print("======================================\n")
    return 0 if report["in_sync"] else 1


if __name__ == "__main__":
    sys.exit(main())
