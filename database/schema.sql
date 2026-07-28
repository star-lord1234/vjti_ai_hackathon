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

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);
