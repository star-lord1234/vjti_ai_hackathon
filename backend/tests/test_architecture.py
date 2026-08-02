"""Unit tests for architectural retrieval gate and clause/rule layers."""

from __future__ import annotations

from retrieval.models import HybridSearchMeta

from reasoning.clause_parser import extract_draft_clauses, format_clauses_for_prompt
from reasoning.retrieval_gate import assess_retrieval_quality, rerank_with_draft_overlap
from reasoning.rule_signals import extract_rule_signals


def test_extract_draft_clauses_finds_sections():
    draft = """
GOVERNMENT OF MAHARASHTRA

Section 4 — Jurisdiction
4.1 State Authorities shall exercise EXCLUSIVE JURISDICTION over environmental impact assessments.

Section 7 — Financial Powers
7.1 Procurement up to Rupees Eighty-Five Crore without prior sanction.
"""
    clauses = extract_draft_clauses(draft)
    assert len(clauses) >= 2
    assert any("EXCLUSIVE" in c for c in clauses)


def test_assess_retrieval_quality_fails_on_empty():
    quality = assess_retrieval_quality([], HybridSearchMeta())
    assert quality["passed"] is False
    assert "No GRs retrieved" in quality["warnings"][0]


def test_assess_retrieval_quality_passes_with_scores():
    results = [{"id": 1, "score": 0.55, "matched_chunk_text": "scholarship"}]
    quality = assess_retrieval_quality(results, HybridSearchMeta(vector_seeds=1))
    assert quality["passed"] is True
    assert quality["chunk_hits"] == 1


def test_rerank_boosts_subject_overlap():
    results = [
        {"id": 1, "score": 0.4, "subject_mr": "ITI scholarship fee"},
        {"id": 2, "score": 0.45, "subject_mr": "unrelated topic"},
    ]
    draft = "ITI scholarship Category B processing timeline"
    reranked = rerank_with_draft_overlap(results, draft)
    assert reranked[0]["id"] == 1
    assert reranked[0]["score"] > 0.4


def test_rule_signals_detects_jurisdiction():
    draft = "State Authorities shall exercise EXCLUSIVE JURISDICTION over EIA reports."
    retrieved = [
        {
            "id": 5,
            "subject_mr": "Environmental clearance",
            "matched_chunk_text": "EXCLUSIVE JURISDICTION over environmental impact",
            "department": "Environment",
        }
    ]
    signals = extract_rule_signals(draft, retrieved)
    types = {s["signal_type"] for s in signals}
    assert "jurisdiction_overlap" in types


def test_format_clauses_for_prompt_nonempty():
    text = format_clauses_for_prompt(["Section 4.2 exclusive jurisdiction clause text here."])
    assert "DRAFT OPERATIVE CLAUSES" in text
