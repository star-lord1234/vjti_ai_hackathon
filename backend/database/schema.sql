CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS gr_documents(
    id BIGSERIAL PRIMARY KEY,
    filename TEXT UNIQUE NOT NULL,
    document_type TEXT,
    document_type_en TEXT,
    department TEXT,
    gr_number_original TEXT,
    gr_number_normalized TEXT,
    gr_number_canonical TEXT,
    department_code TEXT,
    year INTEGER,
    file_number INTEGER,
    subfile_number INTEGER,
    section TEXT,
    gr_date DATE,
    subject_mr TEXT,
    citations JSONB,
    ocr_text TEXT,
    embedding vector(768),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS gr_documents_embedding_hnsw_idx
ON gr_documents USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE TABLE IF NOT EXISTS gr_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES gr_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(768),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS gr_chunks_doc_id_idx ON gr_chunks(document_id);

CREATE INDEX IF NOT EXISTS gr_chunks_embedding_hnsw_idx
ON gr_chunks USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
