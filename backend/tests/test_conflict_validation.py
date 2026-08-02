"""Tests for conflict post-validation and draft path resolution."""

from __future__ import annotations

from reasoning.llm_reasoner import resolve_draft_text
from reasoning.models import ConflictFinding
from reasoning.prompt_utils import apply_conflict_post_validation


def test_resolve_draft_text_does_not_read_bare_short_string(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    probe = tmp_path / "probe.txt"
    probe.write_text("file contents", encoding="utf-8")

    # Short string without path separators — treat as literal draft text
    assert resolve_draft_text("probe.txt") == "probe.txt"


def test_resolve_draft_text_reads_path_with_separator(tmp_path):
    draft = tmp_path / "draft.txt"
    draft.write_text("महाराष्ट्र शासन निर्णय", encoding="utf-8")
    assert "महाराष्ट्र" in resolve_draft_text(str(draft))


def test_apply_conflict_clears_unactionable_conflict():
    finding = ConflictFinding(
        conflicting=True,
        explanation="Possible overlap detected.",
        conflicting_clauses=[],
        affected_grs=[],
        confidence=0.9,
    )
    cleaned = apply_conflict_post_validation(finding, label_map={})
    assert cleaned.conflicting is False
    assert cleaned.confidence <= 0.35
    assert "conflict flag cleared" in cleaned.explanation


def test_apply_conflict_keeps_validated_citations():
    finding = ConflictFinding(
        conflicting=True,
        explanation="Clause conflicts with existing policy.",
        conflicting_clauses=["Section 4.2 exclusive jurisdiction"],
        affected_grs=[],
        confidence=0.8,
    )
    label_map = {"[GR 1]": {"gr_number_canonical": "GR-1"}}
    cleaned = apply_conflict_post_validation(finding, label_map)
    assert cleaned.conflicting is True
    assert len(cleaned.conflicting_clauses) == 1
