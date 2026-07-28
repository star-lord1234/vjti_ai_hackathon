import json
import os
import re
from pathlib import Path

import psycopg


VECTOR_DIM = 768


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
            """
            CREATE INDEX IF NOT EXISTS gr_documents_embedding_hnsw_idx
            ON gr_documents USING hnsw (embedding vector_cosine_ops)
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
            ocr_text = EXCLUDED.ocr_text
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
        for doc_id, canonical in self.cur.fetchall():
            if canonical not in index:
                index[canonical] = doc_id
        return index

    def count(self):
        self.cur.execute("SELECT COUNT(*) FROM gr_documents")
        return self.cur.fetchone()[0]

    def get_documents_for_embedding(self, only_missing: bool = True):
        """Fetch documents needed for generating embeddings."""

        query = """
        SELECT id, filename, gr_number_canonical, department, subject_mr, ocr_text
        FROM gr_documents
        """
        if only_missing:
            query += " WHERE embedding IS NULL"
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

    def search_embeddings(self, query_embedding: str, top_k: int = 20):
        """
        Cosine distance nearest-neighbor search using pgvector <=> operator.
        Returns rows with calculated similarity score (1 - distance).
        """

        query = """
        SELECT id, filename, gr_number_canonical, department, gr_date, subject_mr,
               (embedding <=> %s::vector) AS distance
        FROM gr_documents
        WHERE embedding IS NOT NULL
        ORDER BY distance ASC
        LIMIT %s
        """
        self.cur.execute(query, (str(query_embedding), top_k))
        columns = [desc[0] for desc in self.cur.description]
        results = []
        for row in self.cur.fetchall():
            item = dict(zip(columns, row))
            distance = float(item.pop("distance"))
            item["score"] = 1.0 - distance
            results.append(item)
        return results

    def close(self):
        self.cur.close()
        self.conn.close()

