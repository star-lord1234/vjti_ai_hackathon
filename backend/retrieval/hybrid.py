"""
Hybrid Graph + Vector Retrieval engine for Maharashtra Government Resolutions.
Combines pgvector semantic search (vector seeds) with Neo4j CITES graph expansion.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from database.db import Database
from embeddings.search import semantic_search, semantic_search_multi
from graph.neo4j_query import Neo4jReader
from retrieval.models import GraphExpansionResult, HybridSearchMeta


def _collect_seed_results(
    query: Union[str, List[str]],
    top_k: int,
    db: Optional[Database],
) -> List[Dict[str, Any]]:
    """Run single- or multi-segment semantic search for hybrid seeding."""
    if isinstance(query, list):
        return semantic_search_multi(query, top_k=top_k, db=db)
    if not query or not str(query).strip():
        return []
    return semantic_search(str(query).strip(), top_k=top_k, db=db)


def hybrid_search(
    query: Union[str, List[str]],
    top_k: int = 20,
    hops: int = 1,
    max_results: int = 50,
    db: Optional[Database] = None,
    return_meta: bool = False,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], HybridSearchMeta]]:
    """
    Perform hybrid vector + graph expansion search.

    When hops=0, only vector seeds are returned (no Neo4j expansion).

    Set return_meta=True to receive a HybridSearchMeta alongside results
    (graph degradation, error messages, counts).
    """
    meta = HybridSearchMeta()

    if isinstance(query, str) and not query.strip():
        if return_meta:
            return [], meta
        return []
    if isinstance(query, list) and not any(q and str(q).strip() for q in query):
        if return_meta:
            return [], meta
        return []

    # Step 1: Semantic vector search for top_k seeds
    seed_results = _collect_seed_results(query, top_k=top_k, db=db)
    meta.vector_seeds = len(seed_results)
    seed_ids = [res["id"] for res in seed_results if "id" in res]

    # Step 2: Neo4j graph expansion (skipped when hops=0)
    expansion: GraphExpansionResult = GraphExpansionResult()
    if int(hops) <= 0:
        expansion = GraphExpansionResult(skipped=True)
    elif seed_ids:
        try:
            with Neo4jReader() as reader:
                expansion = reader.expand_citations(seed_ids, hops=hops)
        except Exception as e:
            expansion = GraphExpansionResult(error=str(e))

    meta.graph_skipped = expansion.skipped
    meta.graph_expanded = bool(expansion.nodes) and not expansion.skipped
    meta.graph_error = expansion.error
    meta.graph_degraded = expansion.degraded
    meta.graph_nodes_added = len(expansion.nodes)

    if expansion.error:
        print(
            f"Warning: Neo4j graph expansion failed ({expansion.error}). "
            "Proceeding with vector results only."
        )

    expanded_graph = expansion.nodes

    # Step 3: Combine, deduplicate, and rank candidate entries
    candidates: List[Dict[str, Any]] = []
    seen_ids: set[int] = set()

    for seed in seed_results:
        doc_id = seed["id"]
        seen_ids.add(doc_id)
        candidates.append(
            {
                "id": doc_id,
                "source": "vector",
                "hop_distance": 0,
                "score": seed.get("score"),
                "seed_meta": seed,
            }
        )

    graph_items = []
    for gid, ginfo in expanded_graph.items():
        if gid not in seen_ids:
            seen_ids.add(gid)
            graph_items.append(
                {
                    "id": gid,
                    "source": "graph",
                    "hop_distance": ginfo["hop_distance"],
                    "score": None,
                    "seed_meta": None,
                }
            )

    graph_items.sort(key=lambda x: (x["hop_distance"], x["id"]))
    candidates.extend(graph_items)

    final_candidates = candidates[:max_results]
    if not final_candidates:
        meta.total_results = 0
        if return_meta:
            return [], meta
        return []

    final_ids = [c["id"] for c in final_candidates]

    owns_db = db is None
    database = db or Database()

    try:
        query_sql = """
        SELECT id, filename, gr_number_canonical, department, gr_date, subject_mr
        FROM gr_documents
        WHERE id = ANY(%s)
        """
        database.cur.execute(query_sql, (final_ids,))
        columns = [desc[0] for desc in database.cur.description]
        metadata_by_id = {
            row[0]: dict(zip(columns, row)) for row in database.cur.fetchall()
        }
    finally:
        if owns_db:
            database.close()

    results: List[Dict[str, Any]] = []
    for item in final_candidates:
        doc_id = item["id"]
        meta_row = metadata_by_id.get(doc_id) or (item.get("seed_meta") or {})
        seed = item.get("seed_meta") or {}

        row: Dict[str, Any] = {
            "id": doc_id,
            "filename": meta_row.get("filename"),
            "gr_number_canonical": meta_row.get("gr_number_canonical"),
            "department": meta_row.get("department"),
            "gr_date": meta_row.get("gr_date"),
            "subject_mr": meta_row.get("subject_mr"),
            "source": item["source"],
            "hop_distance": item["hop_distance"],
            "score": item["score"],
        }

        if seed.get("matched_chunk_text"):
            row["matched_chunk_text"] = seed["matched_chunk_text"]
            row["matched_chunk_index"] = seed.get("matched_chunk_index")

        results.append(row)

    meta.total_results = len(results)
    if return_meta:
        return results, meta
    return results


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "AICTE engineering colleges"
    print(f"Executing hybrid search for: '{query}'")
    print("Parameters: top_k=20, hops=1, max_results=50\n")

    results, meta = hybrid_search(query, top_k=20, hops=1, max_results=50, return_meta=True)
    print(f"Retrieval meta: {meta.to_dict()}")
    print(f"Total results returned: {len(results)}\n")

    header = f"{'ID':<8} {'GR Number':<35} {'Department':<30} {'Source':<8} {'Hops':<5} {'Score':<8}"
    print(header)
    print("=" * len(header))

    for r in results:
        score_str = f"{r['score']:.4f}" if r["score"] is not None else "N/A"
        gr_num = str(r["gr_number_canonical"] or "N/A")[:34]
        dept = str(r["department"] or "N/A")[:29]
        source_str = str(r["source"])
        hops_str = str(r["hop_distance"])
        doc_id = str(r["id"])

        print(
            f"{doc_id:<8} {gr_num:<35} {dept:<30} {source_str:<8} {hops_str:<5} {score_str:<8}"
        )


if __name__ == "__main__":
    main()
