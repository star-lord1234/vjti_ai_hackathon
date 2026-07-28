"""
Load GR citation graph into Neo4j from PostgreSQL.

PostgreSQL remains the source of truth. Neo4j is a graph projection only.
This module does not write to PostgreSQL.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

from database.db import Database
from graph.reference_resolver import ReferenceResolver

BATCH_SIZE = int(os.getenv("NEO4J_BATCH_SIZE", "500"))


def _env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _serialize_date(value: Any) -> Optional[str]:
    """Store dates as ISO strings for stable / portable Neo4j properties."""

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _chunks(items: List[Any], size: int) -> Iterable[List[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


class Neo4jLoader:
    """
    Idempotent loader: MERGE nodes and CITES edges from Postgres + resolver.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        db: Optional[Database] = None,
    ):
        self.uri = uri or _env("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or _env("NEO4J_USER", "neo4j")
        self.password = password or _env("NEO4J_PASSWORD")

        self.driver = GraphDatabase.driver(
            self.uri,
            auth=(self.user, self.password),
        )
        self.db = db or Database()
        self._owns_db = db is None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def create_constraints(self) -> None:
        """Create uniqueness constraint on id and index on canonical_gr."""

        statements = [
            # Unique id → also creates a lookup index
            """
            CREATE CONSTRAINT gr_id IF NOT EXISTS
            FOR (g:GR) REQUIRE g.id IS UNIQUE
            """,
            """
            CREATE INDEX gr_canonical IF NOT EXISTS
            FOR (g:GR) ON (g.canonical_gr)
            """,
        ]

        with self.driver.session() as session:
            for cypher in statements:
                session.run(cypher)

        print("Constraints / indexes ready (id UNIQUE, canonical_gr INDEX).")

    # ------------------------------------------------------------------
    # Postgres reads (read-only)
    # ------------------------------------------------------------------

    def fetch_nodes(self) -> List[Dict[str, Any]]:
        """Read GR metadata from PostgreSQL (no OCR)."""

        self.db.cur.execute(
            """
            SELECT
                id,
                filename,
                gr_number_original,
                gr_number_canonical,
                department,
                gr_date,
                subject_mr
            FROM gr_documents
            ORDER BY id
            """
        )

        nodes = []
        for row in self.db.cur.fetchall():
            (
                doc_id,
                filename,
                gr_number,
                canonical_gr,
                department,
                gr_date,
                subject,
            ) = row
            nodes.append(
                {
                    "id": int(doc_id),
                    "filename": filename,
                    "gr_number": gr_number,
                    "canonical_gr": canonical_gr,
                    "department": department,
                    "date": _serialize_date(gr_date),
                    "subject": subject,
                }
            )
        return nodes

    def fetch_edges(self) -> List[Tuple[int, int]]:
        """
        Resolved citation edges (source_id, target_id).

        Computed deterministically via ReferenceResolver (Postgres source of truth).
        """

        resolver = ReferenceResolver(db=self.db)
        try:
            return resolver.resolve_all()
        finally:
            # Do not close shared db
            resolver._owns_db = False

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load_nodes(self, nodes: Optional[List[Dict[str, Any]]] = None) -> int:
        """MERGE all :GR nodes. Returns count loaded."""

        if nodes is None:
            nodes = self.fetch_nodes()

        cypher = """
        UNWIND $batch AS row
        MERGE (g:GR {id: row.id})
        SET g.filename = row.filename,
            g.gr_number = row.gr_number,
            g.canonical_gr = row.canonical_gr,
            g.department = row.department,
            g.date = row.date,
            g.subject = row.subject
        """

        loaded = 0
        with self.driver.session() as session:
            for batch in _chunks(nodes, BATCH_SIZE):
                session.run(cypher, batch=batch)
                loaded += len(batch)
                print(f"  nodes progress: {loaded}/{len(nodes)}", flush=True)

        print(f"Loaded {loaded} nodes")
        return loaded

    def load_edges(self, edges: Optional[List[Tuple[int, int]]] = None) -> int:
        """MERGE all (source)-[:CITES]->(target). Returns relationship count."""

        if edges is None:
            edges = self.fetch_edges()

        # Deduplicate again for safety (idempotent)
        unique_edges = sorted(set((int(s), int(t)) for s, t in edges if s != t))

        cypher = """
        UNWIND $batch AS row
        MATCH (source:GR {id: row.source_id})
        MATCH (target:GR {id: row.target_id})
        MERGE (source)-[:CITES]->(target)
        """

        loaded = 0
        batches = list(_chunks(unique_edges, BATCH_SIZE))
        with self.driver.session() as session:
            for batch in batches:
                payload = [
                    {"source_id": s, "target_id": t} for s, t in batch
                ]
                session.run(cypher, batch=payload)
                loaded += len(batch)
                print(
                    f"  edges progress: {loaded}/{len(unique_edges)}",
                    flush=True,
                )

        print(f"Loaded {loaded} CITES relationships")
        return loaded

    def clear_graph(self) -> None:
        """Delete all nodes and relationships in the Neo4j database."""

        with self.driver.session() as session:
            # Batch delete for larger graphs
            while True:
                result = session.run(
                    """
                    MATCH (n)
                    WITH n LIMIT 10000
                    DETACH DELETE n
                    RETURN count(*) AS deleted
                    """
                )
                deleted = result.single()["deleted"]
                if deleted == 0:
                    break
                print(f"  cleared {deleted} nodes...", flush=True)

        print("Graph cleared.")

    def load_graph(self, clear: bool = False) -> None:
        """
        Full idempotent load:
        constraints → (optional clear) → nodes → edges.
        """

        print(f"Connecting to Neo4j at {self.uri} ...")
        self.driver.verify_connectivity()
        print("Connected.")

        self.create_constraints()

        if clear:
            self.clear_graph()
            self.create_constraints()

        nodes = self.fetch_nodes()
        print(f"Read {len(nodes)} GRs from PostgreSQL.")
        self.load_nodes(nodes)

        print("Resolving citation edges from PostgreSQL...")
        edges = self.fetch_edges()
        print(f"Resolved {len(edges)} unique citation edges.")
        self.load_edges(edges)

        print("Neo4j graph load complete.")

    def close(self) -> None:
        self.driver.close()
        if self._owns_db:
            self.db.close()


def main() -> None:
    clear = "--clear" in sys.argv
    loader = Neo4jLoader()
    try:
        loader.load_graph(clear=clear)
    finally:
        loader.close()


if __name__ == "__main__":
    main()
