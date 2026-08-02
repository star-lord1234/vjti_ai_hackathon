#!/usr/bin/env python3
"""
CI gate for citation → document resolution rate.

Exits 0 when resolution rate meets CITATION_CI_MIN_RESOLUTION_RATE (default 50%).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph.reference_resolver import CitationResolutionError, ReferenceResolver


def main() -> int:
    min_rate = float(os.getenv("CITATION_CI_MIN_RESOLUTION_RATE", "0.50"))
    require_citations = os.getenv("CITATION_CI_REQUIRE_CITATIONS", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    print("=" * 60)
    print("CITATION RESOLUTION QUALITY CHECK")
    print(f"Required rate: {min_rate * 100:.0f}%")
    print("=" * 60)

    resolver = ReferenceResolver()
    try:
        resolver.resolve_all()
        rate = resolver.enforce_resolution_quality(
            min_rate=min_rate,
            require_citations=require_citations,
        )
        print(f"\n>>> PASS: citation resolution rate {rate:.1f}% <<<\n")
        return 0
    except CitationResolutionError as exc:
        print(f"\n>>> FAIL: {exc} <<<\n")
        return 1
    finally:
        resolver.close()


if __name__ == "__main__":
    sys.exit(main())
