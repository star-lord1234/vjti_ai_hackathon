"""
Graph visualization router returning node and link structures for frontend rendering.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graph.neo4j_query import Neo4jReader

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/{gr_id}", response_model=Dict[str, Any])
def get_graph_subgraph(
    gr_id: int,
    hops: int = Query(2, ge=1, le=5, description="Citation path traversal distance"),
) -> Dict[str, Any]:
    """
    Fetch citation subgraph centered on gr_id up to specified hops distance.
    Returns nodes and links format compatible with graph visualization libraries.
    """
    try:
        with Neo4jReader() as reader:
            subgraph = reader.get_subgraph(center_id=gr_id, hops=hops)
            return {
                "center_id": gr_id,
                "hops": hops,
                "nodes": subgraph.get("nodes", []),
                "links": subgraph.get("links", []),
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to query Neo4j graph: {e}")
