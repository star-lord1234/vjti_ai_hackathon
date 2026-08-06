"""
Postgres ↔ Neo4j store sync and embedding drift checks.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Database

SYNC_TOLERANCE = float(os.getenv("STORE_SYNC_TOLERANCE", "0.10"))

# Editable officer drafts are stored in gr_documents but are not corpus retrieval targets.
_CORPUS_EMBED_EXCLUDE = "filename NOT LIKE 'draft-%'"


def check_store_sync(db: Optional[Database] = None) -> Dict[str, Any]:
    """
    Compare Postgres document/embedding state with Neo4j graph coverage.
    Returns warnings when stores may have drifted after partial ingest.
    """
    owns_db = db is None
    database = db or Database()
    warnings: List[str] = []

    try:
        database.cur.execute("SELECT COUNT(*) FROM gr_documents")
        postgres_docs = int(database.cur.fetchone()[0])

        database.cur.execute(
            """
            SELECT COUNT(*) FROM gr_documents
            WHERE ocr_text IS NOT NULL AND length(trim(ocr_text)) > 50
            """
        )
        with_ocr = int(database.cur.fetchone()[0])

        database.cur.execute(
            "SELECT COUNT(*) FROM gr_documents WHERE embedding IS NULL"
        )
        missing_embeddings = int(database.cur.fetchone()[0])

        database.cur.execute(
            f"""
            SELECT COUNT(*) FROM gr_documents d
            WHERE d.ocr_text IS NOT NULL AND length(trim(d.ocr_text)) > 50
              AND d.embedding IS NULL
              AND {_CORPUS_EMBED_EXCLUDE}
            """
        )
        ocr_without_embed = int(database.cur.fetchone()[0])

        chunk_count = database.count_chunks()

        database.cur.execute(
            f"""
            SELECT COUNT(*) FROM gr_documents d
            WHERE d.ocr_text IS NOT NULL AND length(trim(d.ocr_text)) > 50
              AND NOT EXISTS (SELECT 1 FROM gr_chunks c WHERE c.document_id = d.id)
              AND {_CORPUS_EMBED_EXCLUDE}
            """
        )
        ocr_without_chunks = int(database.cur.fetchone()[0])

        neo4j_nodes: Optional[int] = None
        neo4j_edges: Optional[int] = None
        neo4j_ok = False
        try:
            from graph.neo4j_query import Neo4jReader

            with Neo4jReader() as reader:
                neo4j_nodes = reader.count_gr_nodes()
                neo4j_edges = reader.count_cites_edges()
                neo4j_ok = True
        except Exception as exc:
            warnings.append(f"Neo4j sync check unavailable: {exc}")

        if ocr_without_embed > 0:
            warnings.append(
                f"{ocr_without_embed} document(s) have OCR but no embedding — re-run embed."
            )
        if ocr_without_chunks > 0:
            warnings.append(
                f"{ocr_without_chunks} document(s) have OCR but no chunk embeddings."
            )
        if with_ocr > 0 and chunk_count == 0:
            warnings.append("Chunk table empty — clause-level retrieval unavailable.")

        if neo4j_ok and postgres_docs > 0 and neo4j_nodes is not None:
            ratio = abs(postgres_docs - neo4j_nodes) / postgres_docs
            if ratio > SYNC_TOLERANCE:
                warnings.append(
                    f"Postgres/Neo4j count drift: {postgres_docs} docs vs "
                    f"{neo4j_nodes} graph nodes ({ratio:.0%} difference)."
                )
            if neo4j_edges == 0 and postgres_docs > 0:
                warnings.append(
                    "Neo4j has no CITES edges — run graph sync after ingest."
                )

        in_sync = len(warnings) == 0

        return {
            "in_sync": in_sync,
            "postgres_documents": postgres_docs,
            "postgres_with_ocr": with_ocr,
            "missing_embeddings": missing_embeddings,
            "ocr_without_embedding": ocr_without_embed,
            "ocr_without_chunks": ocr_without_chunks,
            "chunk_count": chunk_count,
            "neo4j_gr_nodes": neo4j_nodes,
            "neo4j_cites_edges": neo4j_edges,
            "warnings": warnings,
        }
    finally:
        if owns_db:
            database.close()
