"""Unit tests for context builder OCR slot selection."""

from __future__ import annotations

from reasoning.context_builder import _select_ocr_document_ids


def test_select_ocr_reserves_graph_slots():
    results = [
        {"id": 1, "source": "vector", "score": 0.9},
        {"id": 2, "source": "vector", "score": 0.8},
        {"id": 3, "source": "graph", "hop_distance": 1},
        {"id": 4, "source": "graph", "hop_distance": 2},
        {"id": 5, "source": "vector", "score": 0.7},
    ]
    ocr_ids = _select_ocr_document_ids(results, max_full_text=4)
    assert 3 in ocr_ids or 4 in ocr_ids
    assert len(ocr_ids) <= 4


def test_select_ocr_empty_when_max_zero():
    results = [{"id": 1, "source": "vector", "score": 0.9}]
    assert _select_ocr_document_ids(results, max_full_text=0) == set()
