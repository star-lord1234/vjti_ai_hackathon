"""
Search endpoints router for hybrid vector + graph retrieval and vector-only search.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from embeddings.search import semantic_search
from retrieval.hybrid import hybrid_search

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=List[Dict[str, Any]])
def search_hybrid(
    q: str = Query(..., description="Natural language or keyword search query"),
    top_k: int = Query(20, ge=1, le=100, description="Vector top_k seeds"),
    hops: int = Query(1, ge=0, le=5, description="Graph citation expansion hops"),
    max_results: int = Query(50, ge=1, le=200, description="Maximum total results to return"),
) -> List[Dict[str, Any]]:
    """
    Perform hybrid vector semantic search + Neo4j citation graph expansion.
    """
    query_str = q.strip() if q else ""
    if not query_str:
        raise HTTPException(status_code=400, detail="Query parameter 'q' must not be empty.")

    try:
        results = hybrid_search(
            query=query_str,
            top_k=top_k,
            hops=hops,
            max_results=max_results,
        )

        for item in results:
            if item.get("gr_date") is not None:
                item["gr_date"] = str(item["gr_date"])
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


@router.get("/vector-only", response_model=List[Dict[str, Any]])
def search_vector_only(
    q: str = Query(..., description="Natural language or keyword search query"),
    top_k: int = Query(20, ge=1, le=100, description="Vector top_k results"),
) -> List[Dict[str, Any]]:
    """
    Perform plain vector semantic search (bypassing graph expansion).
    """
    query_str = q.strip() if q else ""
    if not query_str:
        raise HTTPException(status_code=400, detail="Query parameter 'q' must not be empty.")

    try:
        results = semantic_search(query=query_str, top_k=top_k)
        for item in results:
            if item.get("gr_date") is not None:
                item["gr_date"] = str(item["gr_date"])
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {e}")
