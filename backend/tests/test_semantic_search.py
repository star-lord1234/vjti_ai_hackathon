"""Unit tests for embedding search helpers (no DB required)."""

from __future__ import annotations

from embeddings.search import (
    _dedupe_chunks_to_documents,
    _merge_document_results,
    build_draft_query_segments,
)


def test_build_draft_query_segments_short_text_returns_single_segment():
    text = "GOVERNMENT OF MAHARASHTRA\nSubject: ITI scholarship policy"
    segments = build_draft_query_segments(text, segment_chars=600)
    assert segments == [text.strip()]


def test_build_draft_query_segments_splits_long_draft():
    para_a = "Section 4. " + ("State jurisdiction over EIA. " * 40)
    para_b = "Section 7. " + ("Procurement up to eighty five crore. " * 40)
    draft = f"Header line\n\n{para_a}\n\n{para_b}"
    segments = build_draft_query_segments(draft, max_segments=5, segment_chars=400)
    assert len(segments) >= 2
    assert all(len(s) >= 80 for s in segments)


def test_build_draft_query_segments_skips_short_header_paragraphs():
    draft = (
        "महाराष्ट्र शासन\n\n"
        "उच्च व तंत्र शिक्षण विभाग\n\n"
        "Subject: ITI scholarship and fee structure for Category B students "
        "with fifteen working day processing requirement.\n\n"
        + ("Additional operative clause text. " * 30)
    )
    segments = build_draft_query_segments(draft, segment_chars=300, max_segments=5)
    joined = " ".join(segments).lower()
    assert "scholarship" in joined or "शिष्यवृत्ती" in joined


def test_dedupe_chunks_keeps_best_score_per_document():
    chunks = [
        {"id": 1, "score": 0.5, "chunk_index": 0, "chunk_text": "a"},
        {"id": 1, "score": 0.8, "chunk_index": 1, "chunk_text": "b"},
        {"id": 2, "score": 0.7, "chunk_index": 0, "chunk_text": "c"},
    ]
    out = _dedupe_chunks_to_documents(chunks, top_k=5)
    assert len(out) == 2
    by_id = {r["id"]: r for r in out}
    assert by_id[1]["score"] == 0.8
    assert by_id[1]["matched_chunk_index"] == 1


def test_merge_document_results_prefers_higher_score():
    list_a = [{"id": 1, "score": 0.4}, {"id": 2, "score": 0.9}]
    list_b = [{"id": 1, "score": 0.7}, {"id": 3, "score": 0.6}]
    merged = _merge_document_results([list_a, list_b], top_k=10)
    by_id = {r["id"]: r for r in merged}
    assert by_id[1]["score"] == 0.7
    assert len(merged) == 3
