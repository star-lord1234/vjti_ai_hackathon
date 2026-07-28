"""
Hybrid Graph + Vector Retrieval engine for Maharashtra Government Resolutions.
Combines pgvector semantic search (vector seeds) with Neo4j CITES graph expansion.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from database.db import Database
from embeddings.search import semantic_search
from graph.neo4j_query import Neo4jReader


def hybrid_search(
    query: str,
    top_k: int = 20,
    hops: int = 1,
    max_results: int = 50,
    db: Optional[Database] = None,
) -> List[Dict[str, Any]]:
    """
    Perform hybrid vector + graph expansion search.

    Pipeline
    --------
    1. Semantic vector search via pgvector -> top_k seed GRs.
    2. Neo4j graph expansion via CITES relationships up to `hops` distance.
    3. Union & deduplicate candidate sets (vector seeds take precedence).
    4. Batch fetch metadata from PostgreSQL for final candidates.
    5. Return ranked & tagged result list.

    Returns
    -------
    List[Dict[str, Any]]
        List of dicts:
        {
          "id": int,
          "filename": str,
          "gr_number_canonical": str,
          "department": str,
          "gr_date": date / str,
          "subject_mr": str,
          "source": "vector" | "graph",
          "hop_distance": int,
          "score": float | None
        }
    """
    if not query or not query.strip():
        return []

    # Step 1: Semantic vector search for top_k seeds
    seed_results = semantic_search(query, top_k=top_k, db=db)
    seed_ids = [res["id"] for res in seed_results if "id" in res]

    # Step 2: Neo4j graph expansion
    expanded_graph: Dict[int, Dict[str, int]] = {}
    if seed_ids:
        try:
            with Neo4jReader() as reader:
                expanded_graph = reader.expand_citations(seed_ids, hops=hops)
        except Exception as e:
            print(f"Warning: Neo4j graph expansion unavailable ({e}). Proceeding with vector results only.")

    # Step 3: Combine, deduplicate, and rank candidate entries
    candidates: List[Dict[str, Any]] = []
    seen_ids = set()

    # Add vector seeds first (keep vector rank and similarity score)
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

    # Add graph-expanded nodes (unranked by similarity, sorted by hop distance)
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

    # Sort graph items by hop_distance ascending, then by ID for deterministic order
    graph_items.sort(key=lambda x: (x["hop_distance"], x["id"]))
    candidates.extend(graph_items)

    # Cap total candidates at max_results
    final_candidates = candidates[:max_results]
    if not final_candidates:
        return []

    final_ids = [c["id"] for c in final_candidates]

    # Step 4: Batch-fetch full metadata from Postgres for final candidates
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

    # Step 5: Merge metadata into final candidates preserving rank order
    results: List[Dict[str, Any]] = []
    for item in final_candidates:
        doc_id = item["id"]
        meta = metadata_by_id.get(doc_id) or (item.get("seed_meta") or {})

        results.append(
            {
                "id": doc_id,
                "filename": meta.get("filename"),
                "gr_number_canonical": meta.get("gr_number_canonical"),
                "department": meta.get("department"),
                "gr_date": meta.get("gr_date"),
                "subject_mr": meta.get("subject_mr"),
                "source": item["source"],
                "hop_distance": item["hop_distance"],
                "score": item["score"],
            }
        )

    return results


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "AICTE engineering colleges"
    print(f"Executing hybrid search for: '{query}'")
    print("Parameters: top_k=20, hops=1, max_results=50\n")

    results = hybrid_search(query, top_k=20, hops=1, max_results=50)
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
