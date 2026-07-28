"""
Read-only query helper for Neo4j citation graph traversal.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

logger = logging.getLogger(__name__)


def _env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


class Neo4jReader:
    """
    Read-only Neo4j client for expanded graph traversal.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.uri = uri or _env("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or _env("NEO4J_USER", "neo4j")
        self.password = password or _env("NEO4J_PASSWORD")

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
        )

    def __enter__(self) -> Neo4jReader:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def expand_citations(
        self, seed_ids: List[int], hops: int = 1
    ) -> Dict[int, Dict[str, int]]:
        """
        Traverse CITES relationships in both directions up to `hops` distance.

        Parameters
        ----------
        seed_ids : list[int]
            List of seed document IDs from vector search.
        hops : int, default 1
            Maximum path length for graph traversal.

        Returns
        -------
        dict[int, dict]
            Mapping of expanded GR ID -> {"hop_distance": int}.
            Excludes IDs present in seed_ids.
        """
        if not seed_ids:
            return {}

        val_hops = max(1, int(hops))
        clean_seed_ids = [int(i) for i in seed_ids]

        cypher = f"""
        MATCH path = (g:GR)-[:CITES*1..{val_hops}]-(related:GR)
        WHERE g.id IN $seed_ids AND NOT related.id IN $seed_ids
        RETURN related.id AS id, min(length(path)) AS hop_distance
        """

        try:
            with self.driver.session() as session:
                result = session.run(cypher, seed_ids=clean_seed_ids)
                expanded: Dict[int, Dict[str, int]] = {}
                for record in result:
                    node_id = int(record["id"])
                    hop_dist = int(record["hop_distance"])
                    expanded[node_id] = {"hop_distance": hop_dist}
                return expanded
        except Exception as e:
            logger.warning(f"Neo4j graph expansion failed: {e}")
            print(f"Warning: Neo4j graph expansion unavailable ({e}). Continuing with vector results.")
            return {}

    def get_subgraph(
        self, center_id: int, hops: int = 2
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch subgraph around center_id up to hops distance.
        Returns {"nodes": [...], "links": [...]}.
        """
        val_hops = max(1, min(5, int(hops)))
        clean_center_id = int(center_id)

        cypher = f"""
        MATCH path = (c:GR {{id: $center_id}})-[:CITES*0..{val_hops}]-(n:GR)
        UNWIND nodes(path) AS node
        UNWIND relationships(path) AS rel
        RETURN
            collect(DISTINCT {{
                id: node.id,
                gr_number_canonical: coalesce(node.canonical_gr, node.gr_number),
                filename: node.filename,
                department: node.department,
                gr_date: node.date
            }}) AS nodes,
            collect(DISTINCT {{
                source: startNode(rel).id,
                target: endNode(rel).id
            }}) AS links
        """

        try:
            with self.driver.session() as session:
                result = session.run(cypher, center_id=clean_center_id)
                rec = result.single()
                if rec:
                    raw_nodes = rec.get("nodes") or []
                    raw_links = rec.get("links") or []

                    node_map = {}
                    for n in raw_nodes:
                        if n and n.get("id") is not None:
                            node_map[int(n["id"])] = {
                                "id": int(n["id"]),
                                "gr_number_canonical": n.get("gr_number_canonical") or "Unknown",
                                "filename": n.get("filename"),
                                "department": n.get("department") or "Unknown",
                                "gr_date": str(n["gr_date"]) if n.get("gr_date") else None,
                            }

                    link_map = {}
                    for l in raw_links:
                        if l and l.get("source") is not None and l.get("target") is not None:
                            src = int(l["source"])
                            tgt = int(l["target"])
                            link_map[(src, tgt)] = {"source": src, "target": tgt}

                    return {
                        "nodes": list(node_map.values()),
                        "links": list(link_map.values()),
                    }
                return {"nodes": [], "links": []}
        except Exception as e:
            logger.warning(f"Neo4j get_subgraph failed: {e}")
            return {"nodes": [], "links": []}

    def get_cites_edges(self, center_id: int) -> List[Dict[str, Any]]:
        """
        Fetch direct CITES targets for center_id.
        """
        cypher = """
        MATCH (source:GR {id: $center_id})-[r:CITES]->(target:GR)
        RETURN target.id AS id, coalesce(target.canonical_gr, target.gr_number) AS gr_number_canonical, target.filename AS filename
        """
        try:
            with self.driver.session() as session:
                result = session.run(cypher, center_id=int(center_id))
                return [
                    {
                        "id": int(r["id"]),
                        "gr_number_canonical": r["gr_number_canonical"],
                        "filename": r["filename"],
                    }
                    for r in result
                ]
        except Exception as e:
            logger.warning(f"Neo4j get_cites_edges failed: {e}")
            return []

    def close(self) -> None:
        if hasattr(self, "driver") and self.driver:
            self.driver.close()

