"""Unit tests for rule-based GR template checker."""

from __future__ import annotations

from parser.section_locator import locate_header_block, locate_subject_line
from reasoning.template.checker import run_template_check

SAMPLE_WITH_HEADER_SUBJECT_OPERATIVE = """\
महाराष्ट्र शासन
उच्च व तंत्र शिक्षण विभाग

शासन निर्णय क्र. ITI-2024/CR-102/EDU-1

विषय: आयटीआय शिष्यवृत्ती व शुल्क रचनेचे एकत्रीकरण

प्रस्तावना
जेथे आयटीआई विद्यार्थ्यांसाठी शिष्यवृत्ती आवश्यक आहे;

कलम 4 — अधिकारक्षेत्र
4.1 संबंधित विभाग हा विषयाचा नोडल विभाग राहील.

(सचिव)
उच्च व तंत्र शिक्षण विभाग
"""


def test_locate_header_and_subject():
    text = SAMPLE_WITH_HEADER_SUBJECT_OPERATIVE
    header = locate_header_block(text)
    subject = locate_subject_line(text)
    assert header is not None
    assert subject is not None
    assert header.char_offset < subject.char_offset


def test_template_score_counts_missing_signatory():
    draft = """\
महाराष्ट्र शासन
विषय: चाचणी विषय

कलम 1
1.1 ऑपरेटिव्ह तरतूद येथे आहे.
"""
    result = run_template_check(draft)
    assert result.accuracy_score < 100.0
    assert any(v.section_id == "signatory_block" for v in result.violations)
    assert len(result.findings) >= 1
    assert result.findings[0].category == "template"


def test_template_full_structure_high_score():
    result = run_template_check(SAMPLE_WITH_HEADER_SUBJECT_OPERATIVE)
    assert result.accuracy_score >= 75.0
    assert result.sections_present >= 3
    assert all(f.category == "template" for f in result.findings) or not result.findings


def test_template_findings_have_highlight_fields():
    draft = """\
महाराष्ट्र शासन
विषय: चाचणी

कलम 1
1.1 तरतूद.
"""
    result = run_template_check(draft)
    for finding in result.findings:
        assert finding.id.startswith("tpl-")
        assert finding.severity in ("high", "medium", "low")
        assert finding.summary
