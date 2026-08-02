"""Unit tests for citation GR number extraction."""

from __future__ import annotations

from graph.reference_resolver import (
    CitationResolutionError,
    ReferenceResolver,
    extract_gr_number_from_citation,
)


def test_extract_gr_number_from_labelled_citation():
    raw = "शासन निर्णय क्र. ITI-2024/CR-102/EDU-1 दिनांक 01/01/2024"
    result = extract_gr_number_from_citation(raw)
    assert result is not None
    assert "ITI" in result or "2024" in result


def test_extract_gr_number_from_english_no():
    raw = "Reference Circular No. 2018/ENV/047 regarding clearance"
    result = extract_gr_number_from_citation(raw)
    assert result is not None
    assert "2018" in result


def test_extract_gr_number_returns_none_for_noise():
    assert extract_gr_number_from_citation("") is None
    assert extract_gr_number_from_citation("see attached") is None


def test_enforce_resolution_quality_raises_below_threshold():
    resolver = ReferenceResolver.__new__(ReferenceResolver)
    resolver.stats = {
        "documents_processed": 1,
        "references_found": 10,
        "references_resolved": 2,
    }
    try:
        resolver.enforce_resolution_quality(min_rate=0.5, require_citations=True)
        assert False, "expected CitationResolutionError"
    except CitationResolutionError as exc:
        assert "below required" in str(exc)


def test_enforce_resolution_quality_passes_above_threshold():
    resolver = ReferenceResolver.__new__(ReferenceResolver)
    resolver.stats = {
        "documents_processed": 1,
        "references_found": 10,
        "references_resolved": 6,
    }
    rate = resolver.enforce_resolution_quality(min_rate=0.5)
    assert rate == 60.0
