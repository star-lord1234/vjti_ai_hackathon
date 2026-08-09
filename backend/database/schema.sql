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
    status VARCHAR,
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

CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    gr_document_id BIGINT REFERENCES gr_documents(id) ON DELETE CASCADE,
    actor VARCHAR NOT NULL,
    action_type VARCHAR NOT NULL,
    finding_snapshot JSONB,
    diff TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_gr_document_id ON audit_log(gr_document_id);

CREATE TABLE IF NOT EXISTS gr_versions (
    id BIGSERIAL PRIMARY KEY,
    gr_document_id BIGINT REFERENCES gr_documents(id) ON DELETE CASCADE,
    version_number INT NOT NULL,
    full_text TEXT NOT NULL,
    actor VARCHAR(128) DEFAULT 'anonymous',
    lines_added INT DEFAULT 0,
    lines_deleted INT DEFAULT 0,
    chars_added INT DEFAULT 0,
    chars_deleted INT DEFAULT 0,
    raw_diff TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (gr_document_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_gr_versions_gr_document_id ON gr_versions(gr_document_id);
