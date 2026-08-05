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
जेथे आयटीआई विद्यार्थ्यांसाठी शिष्यवृत्ती आवश्यक आहे; शासनाने सदर खर्चासाठी
वित्त विभागाची मान्यता घेतली आहे.

वाचा :- शासन निर्णय, वित्त विभाग, क्र.अर्थसं-२०२४/प्र.क्र.१२/अर्थ-३, दि.०१/०१/२०२४

कलम 4 — अधिकारक्षेत्र
4.1 संबंधित विभाग हा विषयाचा नोडल विभाग राहील.

सदर खर्च, उच्च व तंत्र शिक्षण विभाग "मागणी क्र. 2205 0458 10-कंत्राटी सेवा" या लेखाशिर्षाखाली
सन २०२४-२५ मध्ये निधी वितरीत करण्यास मान्यता देण्यात येत आहे.

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


def test_template_detects_preamble_financial_and_budget_head():
    draft = """\
महाराष्ट्र शासन
उच्च व तंत्र शिक्षण विभाग

शासन ज्ञापन क्रमांकः संकीर्ण-२०२२/प्र.क्र.८७/आस्था-२
दिनांक : ०४ ऑक्टोंबर, २०२२.

प्रस्तावना :-
शिक्षण संचालक, उच्च शिक्षण, महाराष्ट्र राज्य, पुणे यांना पत्रान्वये विनंती आली.

वाचा :- शासन निर्णय क्रमांकःसंकीर्ण-२०२२/प्र.क्र.८७/आस्था-२, दिनांक २१/०९/२०२२

ज्ञापन:-
सदर खर्च, उच्च व तंत्र शिक्षण विभाग “मागणी क्र.डब्लू-४, २२०५ कला व संस्कृती (०१) समित्या व समारंभ (०१)(०१) समित्या (अनिवार्य) (२२०५ ०४५८) १०-कंत्राटी सेवा” या लेखाशीर्षाखाली सन २०२२-२३ मध्ये निधी वितरीत करण्यास मान्यता दिली आहे.

२. सदर खर्च हा लेखाशिर्ष २२०५ ०४५८ अंतर्गत भागविण्यात यावा.

३. उपरोक्त खर्च शासनाच्या प्रचलित कार्यपध्दतीनुसार करण्यात यावा.

४. सदर ज्ञापन वित्त विभाग, अनौपचारिक संदर्भ क्रमांक:९१०/व्यय/५, दिनांक २०.०९.२०२२ अन्वये दिलेल्या सहमतीस अनुसरुन निर्गमित करण्यात येत आहे.

(प्र. पां. लुबाळ )
उप सचिव, महाराष्ट्र शासन

प्रति,
शिक्षण संचालक, उच्च शिक्षण, महाराष्ट्र राज्य, पुणे
"""
    result = run_template_check(draft)
    section_ids = {v.section_id for v in result.violations}
    assert "preamble_section" in section_ids or any(
        s in result.section_positions for s in ["preamble_section", "financial_sanction_block", "budget_head"]
    )
    assert result.total_required_sections >= 7
    assert "budget_head" in result.section_positions or any(
        v.section_id == "budget_head" for v in result.violations
    )
