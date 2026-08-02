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

from retrieval.models import GraphExpansionResult

logger = logging.getLogger(__name__)


def _env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _graph_bidirectional() -> bool:
    return os.getenv("GRAPH_BIDIRECTIONAL", "false").lower() in ("1", "true", "yes")


def check_neo4j_health() -> Dict[str, Any]:
    """Ping Neo4j for health endpoint use."""
    try:
        with Neo4jReader() as reader:
            with reader.driver.session() as session:
                record = session.run("RETURN 1 AS ok").single()
                ok = record is not None and record.get("ok") == 1
        return {"ok": ok, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


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
    ) -> GraphExpansionResult:
        """
        Traverse outgoing CITES relationships from seed GRs up to `hops` distance.

        hops=0 skips graph expansion entirely (vector-only retrieval).
        Set GRAPH_BIDIRECTIONAL=true to use undirected traversal (not recommended).
        """
        if not seed_ids:
            return GraphExpansionResult()

        val_hops = int(hops)
        if val_hops <= 0:
            return GraphExpansionResult(skipped=True)

        clean_seed_ids = [int(i) for i in seed_ids]
        max_per_hop = int(os.getenv("GRAPH_MAX_RESULTS_PER_HOP", "15"))

        if _graph_bidirectional():
            rel = f"-[:CITES*1..{val_hops}]-"
        else:
            rel = f"-[:CITES*1..{val_hops}]->"

        cypher = f"""
        MATCH path = (g:GR){rel}(related:GR)
        WHERE g.id IN $seed_ids AND NOT related.id IN $seed_ids
        WITH related.id AS id, min(length(path)) AS hop_distance
        ORDER BY hop_distance ASC, id ASC
        RETURN id, hop_distance
        LIMIT $limit
        """

        try:
            with self.driver.session() as session:
                result = session.run(
                    cypher,
                    seed_ids=clean_seed_ids,
                    limit=max_per_hop * val_hops,
                )
                expanded: Dict[int, Dict[str, int]] = {}
                for record in result:
                    node_id = int(record["id"])
                    hop_dist = int(record["hop_distance"])
                    expanded[node_id] = {"hop_distance": hop_dist}
                return GraphExpansionResult(nodes=expanded)
        except Exception as e:
            logger.warning("Neo4j graph expansion failed: %s", e)
            return GraphExpansionResult(error=str(e))

    def get_subgraph(
        self, center_id: int, hops: int = 2
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch subgraph around center_id up to hops distance.
        Returns {"nodes": [...], "links": [...]}.
        """
        val_hops = max(1, min(5, int(hops)))
        clean_center_id = int(center_id)

        rel = "-[:CITES*0..{h}]-" if _graph_bidirectional() else "-[:CITES*0..{h}]->"
        rel = rel.format(h=val_hops)

        cypher = f"""
        MATCH path = (c:GR {{id: $center_id}}){rel}(n:GR)
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
            logger.warning("Neo4j get_subgraph failed: %s", e)
            return {"nodes": [], "links": []}

    def count_gr_nodes(self) -> int:
        """Count GR nodes in Neo4j for store-sync checks."""
        try:
            with self.driver.session() as session:
                record = session.run("MATCH (n:GR) RETURN count(n) AS c").single()
                return int(record["c"]) if record else 0
        except Exception as e:
            logger.warning("Neo4j count_gr_nodes failed: %s", e)
            return 0

    def count_cites_edges(self) -> int:
        """Count CITES relationships in Neo4j."""
        try:
            with self.driver.session() as session:
                record = session.run(
                    "MATCH ()-[r:CITES]->() RETURN count(r) AS c"
                ).single()
                return int(record["c"]) if record else 0
        except Exception as e:
            logger.warning("Neo4j count_cites_edges failed: %s", e)
            return 0

    def get_cites_edges(self, center_id: int) -> List[Dict[str, Any]]:
        """
        Fetch direct outgoing CITES targets for center_id.
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
            logger.warning("Neo4j get_cites_edges failed: %s", e)
            return []

    def close(self) -> None:
        if hasattr(self, "driver") and self.driver:
            self.driver.close()
