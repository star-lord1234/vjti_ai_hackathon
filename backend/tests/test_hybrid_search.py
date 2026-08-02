"""Unit tests for hybrid retrieval semantics (mocked DB / Neo4j)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from retrieval.hybrid import hybrid_search
from retrieval.models import GraphExpansionResult


@patch("retrieval.hybrid.Database")
@patch("retrieval.hybrid._collect_seed_results")
def test_hybrid_search_hops_zero_skips_neo4j(mock_seeds, mock_db_cls):
    mock_seeds.return_value = [
        {
            "id": 10,
            "score": 0.82,
            "filename": "a.pdf",
            "gr_number_canonical": "GR-A",
            "department": "Dept",
            "gr_date": None,
            "subject_mr": "Subject A",
        }
    ]

    mock_db = MagicMock()
    mock_db_cls.return_value = mock_db
    mock_db.cur.description = [
        ("id",),
        ("filename",),
        ("gr_number_canonical",),
        ("department",),
        ("gr_date",),
        ("subject_mr",),
    ]
    mock_db.cur.fetchall.return_value = [
        (10, "a.pdf", "GR-A", "Dept", None, "Subject A"),
    ]

    results, meta = hybrid_search("ITI scholarship", top_k=5, hops=0, return_meta=True)

    assert meta.graph_skipped is True
    assert meta.graph_nodes_added == 0
    assert len(results) == 1
    assert results[0]["source"] == "vector"


@patch("retrieval.hybrid.Database")
@patch("retrieval.hybrid.Neo4jReader")
@patch("retrieval.hybrid._collect_seed_results")
def test_hybrid_search_hops_positive_expands_graph(
    mock_seeds, mock_neo4j_reader, mock_db_cls
):
    mock_seeds.return_value = [{"id": 1, "score": 0.9}]

    expansion = GraphExpansionResult(
        nodes={2: {"hop_distance": 1}},
        skipped=False,
    )
    reader_instance = MagicMock()
    reader_instance.expand_citations.return_value = expansion
    reader_instance.__enter__.return_value = reader_instance
    reader_instance.__exit__.return_value = None
    mock_neo4j_reader.return_value = reader_instance

    mock_db = MagicMock()
    mock_db_cls.return_value = mock_db
    mock_db.cur.description = [
        ("id",),
        ("filename",),
        ("gr_number_canonical",),
        ("department",),
        ("gr_date",),
        ("subject_mr",),
    ]
    mock_db.cur.fetchall.return_value = [
        (1, "a.pdf", "GR-A", "Dept", None, "Subj A"),
        (2, "b.pdf", "GR-B", "Dept", None, "Subj B"),
    ]

    results, meta = hybrid_search("query", top_k=5, hops=1, return_meta=True)

    assert meta.graph_skipped is False
    assert meta.graph_nodes_added == 1
    sources = {r["source"] for r in results}
    assert "vector" in sources
    assert "graph" in sources
