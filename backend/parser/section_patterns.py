"""
Shared GR section/header regex patterns used by rule_extractor and template checker.
"""

from __future__ import annotations

import re

DOCUMENT_TYPES = (
    "शासन पूरक पत्र",
    "शासन परिपत्रक",
    "शासन निर्णय",
    "शासन पत्र",
    "कार्यालयीन आदेश",
    "शासन आदेश",
    "अधिसूचना",
)

# Longer phrases first so "शासन पूरक पत्र" wins over "शासन पत्र".
DOC_TYPE_RE = re.compile(
    r"(शासन\s*पूरक\s*पत्र|शासन\s*परिपत्रक|शासन\s*निर्णय|"
    r"शासन\s*पत्र|कार्यालयीन\s*आदेश|शासन\s*आदेश|अधिसूचना)"
)

GOVT_LINE_RE = re.compile(r"महाराष्ट\S*\s*शासन")
GOVT_LINE_EN_RE = re.compile(r"GOVERNMENT\s+OF\s+MAHARASHTRA", re.IGNORECASE)

GR_NUMBER_RE = re.compile(
    r"(?:शासन\s*(?:निर्णय|पत्र|परिपत्रक|आदेश|पूरक\s*पत्र)|"
    r"कार्यालयीन\s*आदेश|अधिसूचना|परिपत्रक)"
    r"\s*,?\s*(?:क्रमांक|कमांक|क्र)\s*[.:ः\-–—]*\s*",
    re.IGNORECASE,
)

SUBJECT_LABEL_RE = re.compile(r"^विषय\s*[.:ः\-–—]*\s*(.*)$")

SUBJECT_STOP = (
    "महाराष्ट्र शासन",
    "महाराष्ट् शासन",
    "महाराष्ट॒ शासन",
    "वाचा",
    "बाचा",
    "संदर्भ",
    "प्रस्तावना",
    "दिनांक",
    "शासन निर्णय",
    "शासन पत्र",
    "शासन परिपत्रक",
    "शासन आदेश",
    "कार्यालयीन आदेश",
    "अधिसूचना",
)

REF_SECTION_START_RE = re.compile(
    r"^(वाचा|बाचा|संदर्भ|Reference)(?:\s|[.:ः\-–—]|$)",
    re.IGNORECASE | re.MULTILINE,
)

REF_SECTION_STOP_RE = re.compile(
    r"^(प्रस्तावना|शासन\s*निर्णय\s*[:：\-]|शासन\s*परिपत्रक\s*[:：\-]|"
    r"परिपत्रक\s*[:：\-]|आदेश\s*[:：\-]|शासन\s*आदेश\s*[:：\-])"
)

PREAMBLE_START_RE = re.compile(r"^प्रस्तावना\b", re.MULTILINE)

# Operative decision block — not the header "शासन निर्णय क्र." line.
OPERATIVE_HEADING_RE = re.compile(
    r"^शासन\s*(?:निर्णय|परिपत्रक|आदेश)\s*[:：\-](?!\s*क्र)",
    re.MULTILINE,
)

OPERATIVE_FALLBACK_RE = re.compile(
    r"^(?:यान्वये|Therefore).{0,160}मंजूर",
    re.MULTILINE | re.IGNORECASE,
)

OPERATIVE_CLAUSE_RE = re.compile(
    r"^(?:कलम|Clause|Section)\s+[\d०१२३४५६७८९]+",
    re.MULTILINE | re.IGNORECASE,
)

SIGNATORY_RE = re.compile(
    r"(?:\(\s*(?:सचिव|उपसचिव|अधिकृत\s+सही|Secretary|Deputy\s+Secretary)\s*\)|"
    r"(?:^|\n)\s*(?:सचिव|Secretary)\s*[,،]?\s*(?:विभाग|Department)|"
    r"(?:^|\n)\s*(?:उपसचिव|Deputy\s+Secretary))",
    re.MULTILINE | re.IGNORECASE,
)

DEPARTMENT_RE = re.compile(r"(विभाग|विश्राग|खाते|Department)", re.IGNORECASE)
