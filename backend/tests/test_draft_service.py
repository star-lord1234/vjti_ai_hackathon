"""Unit tests for draft workflow helpers."""

from __future__ import annotations

from reasoning.glossary.models import GlossaryCheckSection, GlossaryFinding
from reasoning.models import ConflictFinding
from reasoning.template.models import TemplateCheckSection, TemplateViolation
from services.draft import compute_text_diff, has_high_severity_findings


def test_compute_text_diff_empty_when_unchanged():
    text = "महाराष्ट्र शासन\nविषय: चाचणी"
    assert compute_text_diff(text, text) == ""


def test_texts_equal_normalizes_line_endings():
    from services.draft import texts_equal

    assert texts_equal("line one\n", "line one\r\n")
    assert not texts_equal("line one", "line two")
    diff = compute_text_diff("line one\n", "line two\n")
    assert "--- previous" in diff
    assert "+++ current" in diff
    assert "-line one" in diff
    assert "+line two" in diff


def test_has_high_severity_conflict_blocks():
    template = TemplateCheckSection(
        accuracy_score=100,
        total_required_sections=1,
        sections_correct=1,
        sections_present=1,
        violations=[],
        findings=[],
    )
    glossary = GlossaryCheckSection(status="ok", findings=[])
    conflict = ConflictFinding(conflicting=True, explanation="Conflict found")
    assert has_high_severity_findings(
        template_check=template,
        glossary_check=glossary,
        conflict_result=conflict,
    )


def test_has_high_severity_template_violation_blocks():
    template = TemplateCheckSection(
        accuracy_score=50,
        total_required_sections=2,
        sections_correct=1,
        sections_present=1,
        violations=[
            TemplateViolation(
                violation_type="missing",
                section_id="preamble",
                section_label="Preamble",
                severity="high",
                description="Missing preamble",
            )
        ],
        findings=[],
    )
    glossary = GlossaryCheckSection(status="ok", findings=[])
    assert has_high_severity_findings(
        template_check=template,
        glossary_check=glossary,
        conflict_result=ConflictFinding(conflicting=False, explanation="ok"),
    )


def test_has_high_severity_clear_when_no_issues():
    template = TemplateCheckSection(
        accuracy_score=100,
        total_required_sections=1,
        sections_correct=1,
        sections_present=1,
        violations=[],
        findings=[],
    )
    glossary = GlossaryCheckSection(
        status="ok",
        findings=[
            GlossaryFinding(
                text_found="foo",
                context_snippet="foo bar",
                canonical_term="bar",
                reason="test",
                confidence=0.5,
            )
        ],
    )
    assert not has_high_severity_findings(
        template_check=template,
        glossary_check=glossary,
        conflict_result=ConflictFinding(conflicting=False, explanation="ok"),
    )
