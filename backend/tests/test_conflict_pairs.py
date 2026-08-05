"""Tests for draft vs corpus excerpt pairing."""

from __future__ import annotations

from reasoning.models import ConflictFinding, SupportingGR
from reasoning.prompt_utils import (
    _build_per_pair_recommendation,
    build_conflict_pairs,
    extract_corpus_excerpt_for_clause,
)


def test_extract_corpus_excerpt_finds_amount_sentence():
    draft = "Scholarship pay shall be Rs. 25,000 per student per month."
    ocr = (
        "Policy section 9. The competent authority fixes scholarship at "
        "Rs. 24,000 per student per month for Category B applicants."
    )
    excerpt = extract_corpus_excerpt_for_clause(draft, ocr)
    assert "24,000" in excerpt or "24000" in excerpt.replace(",", "")


def test_build_conflict_pairs_links_clause_to_corpus():
    finding = ConflictFinding(
        conflicting=True,
        explanation="Pay amount differs.",
        conflicting_clauses=[
            "Draft sets scholarship at Rs. 25,000 per month.",
        ],
        affected_grs=[
            SupportingGR(
                label="[GR 1]",
                gr_number_canonical="GR-2020-1",
                relevance_note="Scholarship policy",
                corpus_excerpt="Existing GR fixes Rs. 24,000 per month for Category B.",
            )
        ],
        confidence=0.8,
    )
    label_map = {
        "[GR 1]": {
            "gr_number_canonical": "GR-2020-1",
            "ocr_excerpt": "Existing GR fixes Rs. 24,000 per month for Category B.",
        }
    }
    pairs = build_conflict_pairs(finding, label_map)
    assert len(pairs) == 1
    assert "25,000" in pairs[0].draft_clause
    assert "24,000" in pairs[0].corpus_excerpt


def test_recommendations_are_context_specific():
    amount_rec = _build_per_pair_recommendation(
        "The draft grants scholarship of Rs. 1,00,000 against the approved ceiling of Rs. 75,000.",
        "[GR 12]",
        "override",
        "Scholarship ceiling is capped at Rs. 75,000 per beneficiary.",
    )
    authority_rec = _build_per_pair_recommendation(
        "The Principal may approve the claim without the competent authority's sanction.",
        "[GR 6]",
        "inconsistency",
        "Only the competent authority may approve this claim.",
    )

    assert amount_rec != authority_rec
    assert "amount" in amount_rec.lower() or "ceiling" in amount_rec.lower()
    assert "authority" in authority_rec.lower() or "competent" in authority_rec.lower()
