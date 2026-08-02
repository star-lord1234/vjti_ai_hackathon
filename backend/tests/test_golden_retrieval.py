"""Integration tests for golden retrieval set (requires Postgres + embeddings)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval_retrieval import evaluate_case

GOLDEN_FILE = Path(__file__).resolve().parent.parent / "scripts" / "fixtures" / "golden_retrieval.json"


@pytest.fixture(scope="module")
def golden_cases():
    payload = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    return payload.get("cases") or []


@pytest.mark.integration
def test_golden_retrieval_recall(golden_cases, skip_without_db):
    if not golden_cases:
        pytest.skip("No golden retrieval cases defined")

    failures = []
    for case in golden_cases:
        outcome = evaluate_case(case, use_hybrid=True)
        if not outcome["passed"]:
            failures.append(
                f"{outcome['id']}: hits={outcome['hits_at_k']} "
                f"(need {outcome['min_recall_at_k']})"
            )

    assert not failures, "Golden retrieval misses:\n" + "\n".join(failures)
