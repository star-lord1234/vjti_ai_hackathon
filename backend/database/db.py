import json
import os
import re
import threading
from pathlib import Path

import psycopg


VECTOR_DIM = int(os.getenv("VECTOR_DIM", "768"))
HNSW_M = int(os.getenv("HNSW_M", "16"))
HNSW_EF_CONSTRUCTION = int(os.getenv("HNSW_EF_CONSTRUCTION", "64"))

_schema_lock = threading.Lock()
_schema_initialized = False


class Database:

    def __init__(
        self,
        dbname=None,
        user=None,
        password=None,
        host=None,
        port=None,
    ):

        dbname = dbname or os.getenv("POSTGRES_DB", "maha_gr")
        user = user or os.getenv("POSTGRES_USER") or os.getenv("USER") or "postgres"
        password = password if password is not None else os.getenv("POSTGRES_PASSWORD")
        host = host or os.getenv("POSTGRES_HOST", "localhost")
        port = int(port or os.getenv("POSTGRES_PORT", "5432"))

        self.conn = psycopg.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port,
        )

        self.cur = self.conn.cursor()
        self.ensure_schema()

    def ensure_schema(self):
        """Create table / add columns / indexes needed for JSON ingest and embeddings."""
        global _schema_initialized

        if _schema_initialized:
            return

        with _schema_lock:
            if _schema_initialized:
                return

            self._apply_schema_migrations()
            _schema_initialized = True

    def _apply_schema_migrations(self):
        """Run idempotent DDL once per process (avoids concurrent migration deadlocks)."""

        self.cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        schema_path = Path(__file__).resolve().parent / "schema.sql"
        self.cur.execute(schema_path.read_text(encoding="utf-8"))

        # Full department name from metadata JSON (not only parsed code)
        self.cur.execute(
            """
            ALTER TABLE gr_documents
            ADD COLUMN IF NOT EXISTS department TEXT
            """
        )

        # Vector embedding column & HNSW index for Phase 3 semantic search
        self.cur.execute(
            f"""
            ALTER TABLE gr_documents
            ADD COLUMN IF NOT EXISTS embedding vector({VECTOR_DIM})
            """
        )

        self.cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS gr_chunks (
                id BIGSERIAL PRIMARY KEY,
                document_id BIGINT NOT NULL REFERENCES gr_documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding vector({VECTOR_DIM}),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        self.cur.execute(
            """
            CREATE INDEX IF NOT EXISTS gr_chunks_doc_id_idx ON gr_chunks(document_id)
            """
        )

        self.cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS gr_documents_embedding_hnsw_idx
            ON gr_documents USING hnsw (embedding vector_cosine_ops)
            WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})
            """
        )

        self.cur.execute(
            f"""
            CREATE INDEX IF NOT EXISTS gr_chunks_embedding_hnsw_idx
            ON gr_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = {HNSW_M}, ef_construction = {HNSW_EF_CONSTRUCTION})
            """
        )

        self.cur.execute(
            """
            ALTER TABLE gr_documents
            ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'draft'
            """
        )

        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                gr_document_id BIGINT REFERENCES gr_documents(id) ON DELETE CASCADE,
                actor VARCHAR NOT NULL,
                action_type VARCHAR NOT NULL,
                finding_snapshot JSONB,
                diff TEXT,
                created_at TIMESTAMPTZ DEFAULT now()
            )
            """
        )

        self.cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_audit_log_gr_document_id
            ON audit_log(gr_document_id)
            """
        )

        self.cur.execute(
            """
            CREATE TABLE IF NOT EXISTS gr_versions (
                id BIGSERIAL PRIMARY KEY,
                gr_document_id BIGINT REFERENCES gr_documents(id) ON DELETE CASCADE,
                version_number INT NOT NULL,
                full_text TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                UNIQUE (gr_document_id, version_number)
            )
            """
        )

        self.cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_gr_versions_gr_document_id
            ON gr_versions(gr_document_id)
            """
        )

        # Corpus rows should not inherit editable-draft workflow status.
        self.cur.execute(
            """
            UPDATE gr_documents
            SET status = NULL
            WHERE filename NOT LIKE 'draft-%'
              AND status = 'draft'
            """
        )

        self.conn.commit()


    def insert_document(self, metadata, commit=True):
        """Upsert one document from normalized metadata + ocr_text."""

        query = """
        INSERT INTO gr_documents(

            filename,

            document_type,
            document_type_en,

            department,

            gr_number_original,
            gr_number_normalized,
            gr_number_canonical,

            department_code,
            year,
            file_number,
            subfile_number,
            section,

            gr_date,

            subject_mr,

            citations,

            ocr_text

        )

        VALUES (

            %(filename)s,

            %(document_type)s,
            %(document_type_en)s,

            %(department)s,

            %(gr_number_original)s,
            %(gr_number_normalized)s,
            %(gr_number_canonical)s,

            %(department_code)s,
            %(year)s,
            %(file_number)s,
            %(subfile_number)s,
            %(section)s,

            %(date)s,

            %(subject)s,

            %(citations)s,

            %(ocr_text)s

        )

        ON CONFLICT (filename) DO UPDATE SET

            document_type = EXCLUDED.document_type,
            document_type_en = EXCLUDED.document_type_en,
            department = EXCLUDED.department,
            gr_number_original = EXCLUDED.gr_number_original,
            gr_number_normalized = EXCLUDED.gr_number_normalized,
            gr_number_canonical = EXCLUDED.gr_number_canonical,
            department_code = EXCLUDED.department_code,
            year = EXCLUDED.year,
            file_number = EXCLUDED.file_number,
            subfile_number = EXCLUDED.subfile_number,
            section = EXCLUDED.section,
            gr_date = EXCLUDED.gr_date,
            subject_mr = EXCLUDED.subject_mr,
            citations = EXCLUDED.citations,
            ocr_text = EXCLUDED.ocr_text,
            embedding = CASE
                WHEN gr_documents.ocr_text IS DISTINCT FROM EXCLUDED.ocr_text
                  OR gr_documents.subject_mr IS DISTINCT FROM EXCLUDED.subject_mr
                  OR gr_documents.department IS DISTINCT FROM EXCLUDED.department
                THEN NULL
                ELSE gr_documents.embedding
            END
        """

        data = metadata.copy()

        data["citations"] = json.dumps(
            metadata.get("references", []),
            ensure_ascii=False,
        )

        # Prefer explicit normalised field from JSON when present
        if metadata.get("gr_normalised") and not data.get("gr_number_normalized"):
            data["gr_number_normalized"] = metadata["gr_normalised"]

        # Invalid / non-ISO dates → NULL for Postgres DATE
        date_val = data.get("date")
        if date_val:
            marathi = str.maketrans("०१२३४५६७८९", "0123456789")
            date_val = str(date_val).translate(marathi).strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_val):
                try:
                    from datetime import date as _date
                    y, m, d = map(int, date_val.split("-"))
                    _date(y, m, d)  # raises on 2006-11-31 etc.
                    data["date"] = date_val
                except ValueError:
                    data["date"] = None
            else:
                data["date"] = None
        else:
            data["date"] = None

        data.setdefault("department", metadata.get("department"))

        self.cur.execute(query, data)
        
        # If document OCR or metadata changed, delete stale chunk embeddings
        self.cur.execute(
            """
            DELETE FROM gr_chunks
            WHERE document_id IN (
                SELECT id FROM gr_documents WHERE filename = %s AND embedding IS NULL
            )
            """,
            (data["filename"],),
        )

        if commit:
            self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def commit(self):
        self.conn.commit()

    def get_all_documents(self):

        self.cur.execute("SELECT * FROM gr_documents")
        return self.cur.fetchall()

    def get_by_gr(self, canonical):

        self.cur.execute(
            """
            SELECT *
            FROM gr_documents
            WHERE gr_number_canonical=%s
            """,
            (canonical,),
        )
        return self.cur.fetchone()

    def get_documents_for_resolution(self):
        """Rows needed for citation resolution: id + citations JSON."""

        self.cur.execute(
            """
            SELECT id, citations
            FROM gr_documents
            ORDER BY id
            """
        )

        docs = []
        for doc_id, citations in self.cur.fetchall():
            if citations is None:
                citations = []
            elif isinstance(citations, str):
                citations = json.loads(citations)
            docs.append({"id": doc_id, "citations": citations})
        return docs

    def build_canonical_index(self):
        """
        Map gr_number_canonical -> document id.
        If duplicates exist, keep the lowest id (deterministic).

        Returns
        -------
        tuple[dict, list]
            (index, duplicates) where duplicates is a list of
            (canonical, kept_id, duplicate_id) tuples.
        """

        self.cur.execute(
            """
            SELECT id, gr_number_canonical
            FROM gr_documents
            WHERE gr_number_canonical IS NOT NULL
              AND gr_number_canonical <> ''
            ORDER BY id
            """
        )

        index = {}
        duplicates = []
        for doc_id, canonical in self.cur.fetchall():
            if canonical not in index:
                index[canonical] = doc_id
            else:
                duplicates.append((canonical, index[canonical], doc_id))

        if duplicates:
            import logging
            logging.getLogger(__name__).warning(
                "Duplicate gr_number_canonical values: %d (keeping lowest id)",
                len(duplicates),
            )

        return index, duplicates

    def count(self):
        self.cur.execute("SELECT COUNT(*) FROM gr_documents")
        return self.cur.fetchone()[0]

    def get_documents_for_embedding(self, only_missing: bool = True):
        """Fetch documents needed for generating embeddings."""

        query = """
        SELECT id, filename, gr_number_canonical, department, subject_mr, ocr_text
        FROM gr_documents
        WHERE filename NOT LIKE 'draft-%'
        """
        if only_missing:
            query += """
              AND (
                embedding IS NULL
                OR NOT EXISTS (
                    SELECT 1 FROM gr_chunks c WHERE c.document_id = gr_documents.id
                )
              )
            """
        query += " ORDER BY id"

        self.cur.execute(query)
        columns = [desc[0] for desc in self.cur.description]
        return [dict(zip(columns, row)) for row in self.cur.fetchall()]

    def update_embedding(self, doc_id: int, embedding_val, commit: bool = True):
        """Update vector embedding for a single document."""

        self.cur.execute(
            "UPDATE gr_documents SET embedding = %s WHERE id = %s",
            (str(embedding_val), doc_id),
        )
        if commit:
            self.conn.commit()

    def update_embeddings_batch(self, batch: list, commit: bool = True):
        """
        Batch update vector embeddings.
        batch is a list of tuples: (embedding_str, doc_id)
        """

        self.cur.executemany(
            "UPDATE gr_documents SET embedding = %s WHERE id = %s",
            batch,
        )
        if commit:
            self.conn.commit()

    def delete_chunks_for_document(self, doc_id: int, commit: bool = True):
        """Delete existing chunks for a single document."""
        self.cur.execute("DELETE FROM gr_chunks WHERE document_id = %s", (doc_id,))
        if commit:
            self.conn.commit()

    def insert_chunks_batch(self, batch: list, commit: bool = True):
        """
        Batch insert chunks into gr_chunks.
        batch is a list of tuples: (doc_id, chunk_index, chunk_text, embedding_str)
        """
        query = """
        INSERT INTO gr_chunks (document_id, chunk_index, chunk_text, embedding)
        VALUES (%s, %s, %s, %s::vector)
        """
        self.cur.executemany(query, batch)
        if commit:
            self.conn.commit()

    def search_embeddings(
        self,
        query_embedding: str,
        top_k: int = 20,
        min_score: float = None,
    ):
        """
        Cosine distance nearest-neighbor search on gr_documents using pgvector <=> operator.
        Includes HNSW ef_search recall tuning and optional min_score filtering.
        """
        ef_search = int(os.getenv("HNSW_EF_SEARCH", "64"))
        try:
            self.cur.execute(f"SET LOCAL hnsw.ef_search = {ef_search};")
        except Exception:
            pass

        query = """
        SELECT id, filename, gr_number_canonical, department, gr_date, subject_mr,
               (embedding <=> %s::vector) AS distance
        FROM gr_documents
        WHERE embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT %s
        """
        fetch_limit = top_k * 2 if min_score is not None else top_k
        self.cur.execute(query, (str(query_embedding), fetch_limit))
        columns = [desc[0] for desc in self.cur.description]
        results = []
        for row in self.cur.fetchall():
            item = dict(zip(columns, row))
            distance = float(item.pop("distance"))
            score = 1.0 - distance
            if min_score is not None and score < min_score:
                continue
            item["score"] = score
            results.append(item)
            if len(results) >= top_k:
                break
        return results

    def count_chunks(self) -> int:
        self.cur.execute("SELECT COUNT(*) FROM gr_chunks")
        return self.cur.fetchone()[0]

    def search_chunks(
        self,
        query_embedding: str,
        top_k: int = 20,
        min_score: float = None,
    ):
        """
        Cosine distance nearest-neighbor search on gr_chunks using pgvector <=> operator.
        Returns matching document metadata + chunk information.
        """
        ef_search = int(os.getenv("HNSW_EF_SEARCH", "64"))
        try:
            self.cur.execute(f"SET LOCAL hnsw.ef_search = {ef_search};")
        except Exception:
            pass

        query = """
        SELECT c.document_id AS id, d.filename, d.gr_number_canonical, d.department, d.gr_date, d.subject_mr,
               c.chunk_index, c.chunk_text, (c.embedding <=> %s::vector) AS distance
        FROM gr_chunks c
        JOIN gr_documents d ON c.document_id = d.id
        WHERE c.embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT %s
        """
        fetch_limit = top_k * 3
        self.cur.execute(query, (str(query_embedding), fetch_limit))
        columns = [desc[0] for desc in self.cur.description]
        results = []
        for row in self.cur.fetchall():
            item = dict(zip(columns, row))
            distance = float(item.pop("distance"))
            score = 1.0 - distance
            if min_score is not None and score < min_score:
                continue
            item["score"] = score
            results.append(item)
            if len(results) >= top_k:
                break
        return results

    def get_by_id(self, doc_id: int):
        """Fetch a single document row by ID."""
        self.cur.execute(
            """
            SELECT id, filename, document_type, document_type_en, department,
                   gr_number_original, gr_number_normalized, gr_number_canonical,
                   department_code, year, file_number, subfile_number, section,
                   gr_date, subject_mr, citations, ocr_text, status
            FROM gr_documents
            WHERE id = %s
            """,
            (doc_id,),
        )
        row = self.cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in self.cur.description]
        item = dict(zip(cols, row))
        if item.get("citations") and isinstance(item["citations"], str):
            try:
                item["citations"] = json.loads(item["citations"])
            except Exception:
                pass
        if item.get("gr_date"):
            item["gr_date"] = str(item["gr_date"])
        return item

    def get_paginated_documents(
        self,
        page: int = 1,
        page_size: int = 20,
        department: str = None,
        search: str = None,
    ):
        """Fetch paginated documents with optional department and search filters."""
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        offset = (page - 1) * page_size

        where_clauses = []
        params = []

        if department and department.strip():
            where_clauses.append("department = %s")
            params.append(department.strip())

        if search and search.strip():
            s = f"%{search.strip()}%"
            where_clauses.append("(subject_mr ILIKE %s OR gr_number_canonical ILIKE %s OR gr_number_original ILIKE %s)")
            params.extend([s, s, s])

        where_str = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_sql = f"SELECT COUNT(*) FROM gr_documents{where_str}"
        self.cur.execute(count_sql, tuple(params))
        total = self.cur.fetchone()[0]

        query_sql = f"""
        SELECT id, filename, document_type, document_type_en, department,
               gr_number_original, gr_number_normalized, gr_number_canonical,
               department_code, year, gr_date, subject_mr
        FROM gr_documents
        {where_str}
        ORDER BY id ASC
        LIMIT %s OFFSET %s
        """
        self.cur.execute(query_sql, tuple(params) + (page_size, offset))
        cols = [desc[0] for desc in self.cur.description]
        items = []
        for row in self.cur.fetchall():
            doc = dict(zip(cols, row))
            if doc.get("gr_date"):
                doc["gr_date"] = str(doc["gr_date"])
            items.append(doc)

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def create_draft_document(
        self,
        filename: str,
        full_text: str,
        *,
        subject_mr: str | None = None,
        commit: bool = True,
    ) -> int:
        """Insert a new editable draft row and initial version 1."""
        self.cur.execute(
            """
            INSERT INTO gr_documents (filename, subject_mr, ocr_text, status)
            VALUES (%s, %s, %s, 'draft')
            RETURNING id
            """,
            (filename, subject_mr, full_text),
        )
        doc_id = int(self.cur.fetchone()[0])
        self.cur.execute(
            """
            INSERT INTO gr_versions (gr_document_id, version_number, full_text)
            VALUES (%s, 1, %s)
            """,
            (doc_id, full_text),
        )
        if commit:
            self.conn.commit()
        return doc_id

    def get_draft_document(self, gr_document_id: int):
        """Fetch draft metadata including status and latest version number."""
        self.cur.execute(
            """
            SELECT d.id, d.filename, d.status, d.subject_mr, d.ocr_text,
                   COALESCE(v.version_number, 1) AS version_number,
                   COALESCE(v.full_text, d.ocr_text, '') AS full_text
            FROM gr_documents d
            LEFT JOIN LATERAL (
                SELECT version_number, full_text
                FROM gr_versions
                WHERE gr_document_id = d.id
                ORDER BY version_number DESC
                LIMIT 1
            ) v ON TRUE
            WHERE d.id = %s
            """,
            (gr_document_id,),
        )
        row = self.cur.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in self.cur.description]
        return dict(zip(cols, row))

    def get_latest_version_text(self, gr_document_id: int) -> str | None:
        self.cur.execute(
            """
            SELECT full_text
            FROM gr_versions
            WHERE gr_document_id = %s
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (gr_document_id,),
        )
        row = self.cur.fetchone()
        return row[0] if row else None

    def get_next_version_number(self, gr_document_id: int) -> int:
        self.cur.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM gr_versions
            WHERE gr_document_id = %s
            """,
            (gr_document_id,),
        )
        return int(self.cur.fetchone()[0])

    def insert_gr_version(
        self,
        gr_document_id: int,
        version_number: int,
        full_text: str,
        *,
        commit: bool = False,
    ) -> None:
        self.cur.execute(
            """
            INSERT INTO gr_versions (gr_document_id, version_number, full_text)
            VALUES (%s, %s, %s)
            """,
            (gr_document_id, version_number, full_text),
        )
        if commit:
            self.conn.commit()

    def update_draft_text_and_status(
        self,
        gr_document_id: int,
        full_text: str,
        status: str,
        *,
        commit: bool = False,
    ) -> None:
        self.cur.execute(
            """
            UPDATE gr_documents
            SET ocr_text = %s, status = %s
            WHERE id = %s
            """,
            (full_text, status, gr_document_id),
        )
        if commit:
            self.conn.commit()

    def close(self):
        self.cur.close()
        self.conn.close()


