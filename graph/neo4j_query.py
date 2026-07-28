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

    def close(self) -> None:
        if hasattr(self, "driver") and self.driver:
            self.driver.close()
