# Maharashtra GR Metadata & Citation Graph

Pipeline for extracting structured metadata from Maharashtra Government Resolution (GR) OCR text, storing it in **PostgreSQL**, resolving citations, and projecting a citation graph into **Neo4j**.

```
OCR fulltext (.txt)
        │
        ▼
┌───────────────────┐
│ Rule extractor    │  regex / heuristics (fast, no API)
└─────────┬─────────┘
          │ missing fields only
          ▼
┌───────────────────┐
│ Groq LLM backfill │  optional; skipped when rules succeed
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ normalize.py      │  digits, GR canonical form, etc.
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ PostgreSQL        │  source of truth (metadata + OCR)
│ gr_documents      │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Citation resolver │  deterministic GR matching (no LLM)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Neo4j             │  graph projection (:GR)-[:CITES]->(:GR)
└───────────────────┘
```

---

## What this project does

### 1. Hybrid metadata extraction
- **`parser/rule_extractor.py`** — extracts `document_type`, `department`, `gr_number`, `date`, `subject`, and `references` (वाचा / संदर्भ) from the document header using regex only.
- **`scripts/extract_metadata.py`** — two-phase runner:
  - **Phase 1:** parallel rule extraction; writes a JSON for every file under `metadata/`.
  - **Phase 2:** Groq LLM fills only missing fields (shared-org rate limits are paced).
- Also writes **`gr_normalised`** (uniform GR number) into each JSON.
- On this corpus (~6076 files), rules alone complete most documents; LLM is only for gaps.

### 2. PostgreSQL ingest
- **`scripts/ingest.py`** + **`database/db.py`** upsert each JSON plus the matching OCR file into `gr_documents`.
- Full OCR text lives in column **`ocr_text`** (not copied into Neo4j).

### 3. Citation resolution
- **`graph/reference_resolver.py`** reads citations from Postgres, extracts a GR number, normalizes it via **`parser/normalize.py`**, and matches `gr_number_canonical`.
- Output: unique `(source_id, target_id)` edges. Unmatched citations are ignored (no hallucinated links).

### 4. Neo4j graph load
- **`graph/neo4j_loader.py`** creates `:GR` nodes and `CITES` relationships with `MERGE` (idempotent).
- Node properties: `id`, `filename`, `gr_number`, `canonical_gr`, `department`, `date`, `subject`.

---

## Repository layout

```
vjti/
├── parser/
│   ├── metadata.py          # Pydantic models (GRMetadata, Reference)
│   ├── rule_extractor.py    # Regex / heuristic extraction
│   ├── normalize.py         # GR/subject/date normalization
│   └── utils.py
├── scripts/
│   ├── api_manager.py       # Groq multi-key client + cooldowns
│   ├── extract_metadata.py  # Hybrid extraction → metadata/*.json
│   └── ingest.py            # JSON + OCR → PostgreSQL
├── database/
│   ├── db.py                # Postgres access
│   └── schema.sql           # gr_documents DDL
├── graph/
│   ├── reference_resolver.py
│   ├── neo4j_loader.py
│   └── neo4j_query.py       # Read-only Neo4j CITES citation graph reader
├── embeddings/
│   ├── embed_text.py        # Text representation builder
│   ├── embed.py             # Batch embedding generator & Postgres updater
│   └── search.py            # pgvector semantic search query CLI & API
├── retrieval/
│   ├── __init__.py
│   └── hybrid.py            # Hybrid vector + graph expansion search engine
├── reasoning/
│   ├── __init__.py
│   ├── context_builder.py   # RAG prompt context builder & excerpt manager
│   ├── models.py            # Pydantic schemas (QueryAnswer, ConflictFinding, etc.)
│   └── llm_reasoner.py      # LLM reasoning engine & CLI (Q&A, compare, conflict)

├── maha_grs 2/maha_grs/fulltext/   # OCR .txt inputs (local / not in git)
├── metadata/                       # Generated JSON (local / not in git)
├── .env.example
├── requirements.txt
└── README.md

```

---

## Prerequisites

| Tool | Notes |
|------|--------|
| Python 3.10+ | Developed with 3.14 locally |
| PostgreSQL 14+ | Local server |
| Neo4j 5+ | Neo4j Desktop or local server |
| Groq API keys | Only needed for LLM backfill |

OCR corpus path expected by the scripts:

`maha_grs 2/maha_grs/fulltext/*.txt`

Place your text dumps there (this folder is gitignored because it is large).

---

## Quick start (clone → run)

### 1. Clone and create a venv

```bash
git clone <your-repo-url>
cd vjti

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment file

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Groq (optional if you only ingest existing metadata/)
GROQ_API_KEY_1=gsk_...
GROQ_API_KEY_2=          # optional extras
GROQ_API_KEY_3=

# PostgreSQL
POSTGRES_DB=maha_gr
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_pg_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
```

**Never commit `.env`.** It is listed in `.gitignore`.

### 3. PostgreSQL setup

```bash
# create role/db if needed (example)
createuser -s postgres          # if not already present
createdb maha_gr

# or via psql:
psql -d postgres -c "CREATE DATABASE maha_gr;"
```

Schema is applied automatically on first `Database()` connect (`database/schema.sql` + migrations in `db.py`).

Verify:

```bash
psql -d maha_gr -c "\dt"
```

### 4. Neo4j setup (Desktop)

1. Install [Neo4j Desktop](https://neo4j.com/download/).
2. Create / start a local DBMS.
3. Set password; put the same values in `.env` (`NEO4J_URI` is usually `bolt://localhost:7687`).
4. Start the DBMS (must be running before `neo4j_loader`).

### 5. Put OCR files in place

```text
maha_grs 2/maha_grs/fulltext/*.txt
```

### 6. Extract metadata → JSON

```bash
python scripts/extract_metadata.py
```

- Writes `metadata/<same-name>.json` for every `.txt`.
- Safe to re-run (skips complete files; backfills gaps when API quota allows).
- If Groq hits daily limits, the run pauses; JSONs already written stay valid.

Optional env knobs:

| Variable | Default | Meaning |
|----------|---------|---------|
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Chat model for backfill |
| `RULE_WORKERS` | `~32` | Parallel rule extraction |
| `LLM_WORKERS` | `1` | Concurrent LLM calls (keep low if keys share one org) |
| `MIN_REQUEST_GAP` | `0.35` | Seconds between LLM requests |

### 7. Ingest into PostgreSQL

```bash
python scripts/ingest.py
```

Upserts all `metadata/*.json` rows and attaches OCR from `fulltext`.

Check one row:

```bash
psql -d maha_gr -c "
SELECT filename, document_type, department, gr_number_original,
       gr_date, length(ocr_text)
FROM gr_documents
LIMIT 1;
"
```

### 8. Resolve citations & load Neo4j

```bash
# Print resolution stats + edge sample
python -m graph.reference_resolver

# Load graph (MERGE = idempotent)
python -m graph.neo4j_loader

# Optional: wipe Neo4j graph then reload
python -m graph.neo4j_loader --clear
```

---

## Viewing the graph

### Neo4j Browser
Open **Neo4j Browser** from Desktop, then:

```cypher
MATCH (a:GR)-[r:CITES]->(b:GR)
RETURN a, r, b
LIMIT 25
```

### Neo4j Bloom
1. Desktop → start DBMS → open **Bloom** (Studio → Bloom).
2. Connect to the same bolt URL / credentials.
3. Search e.g. `GR CITES GR`, or run Cypher:

```cypher
MATCH (a:GR)-[r:CITES]->(b:GR)
RETURN a, r, b
LIMIT 50
```

4. Set node captions to `gr_number` or `filename` in the Perspective drawer for readable labels.

---

## PostgreSQL schema (`gr_documents`)

| Column | Purpose |
|--------|---------|
| `id` | Primary key (used as Neo4j node `id`) |
| `filename` | Unique OCR filename |
| `document_type` / `document_type_en` | e.g. शासन निर्णय |
| `department` | Issuing department |
| `gr_number_original` | As extracted |
| `gr_number_normalized` | Digits/spacing cleaned |
| `gr_number_canonical` | Match key for citations |
| `gr_date` | Issue date |
| `subject_mr` | Subject |
| `citations` | JSONB array of `{raw, date}` |
| `ocr_text` | Full OCR (Postgres only) |

---

## Public Python APIs (useful snippets)

```python
from parser.rule_extractor import rule_extract, get_missing_fields
from scripts.extract_metadata import extract_metadata
from graph.reference_resolver import ReferenceResolver
from graph.neo4j_loader import Neo4jLoader

# Rules only
meta = rule_extract(text, filename="doc.txt")

# Hybrid (rules + LLM for gaps)
meta = extract_metadata(text, filename="doc.txt")

# Citation edges for Neo4j
pairs = ReferenceResolver().resolve_all()   # list[(source_id, target_id)]

# Full Neo4j load
loader = Neo4jLoader()
loader.load_graph()
loader.close()
```

---

## Design notes

- **Postgres is source of truth**; Neo4j is a disposable projection.
- **No LLM in citation resolution** — only regex + `normalize.py`.
- **Idempotent Neo4j load** via `MERGE` on node `id` and `CITES` edges.
- **OCR is never stored in Neo4j** (keeps the graph lean).
- Resolution rate on this corpus is modest (~10–15%): many citations point to letters, other departments, or GRs outside the dataset. Unmatched refs are skipped on purpose.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `No Groq API keys found` | Set `GROQ_API_KEY_1` in `.env` |
| Postgres connection errors | Check `POSTGRES_*` in `.env`; ensure `maha_gr` exists |
| Neo4j `ServiceUnavailable` | Start the DBMS in Desktop; check URI/password |
| Empty Bloom scene | Run `neo4j_loader` first; then search `GR CITES GR` |
| LLM phase very slow / paused | Free-tier / shared-org quotas; re-run later — JSON resume is supported |
| Hardcoded old DB user | Prefer `POSTGRES_USER` in `.env` (see `database/db.py`) |

---

## License / data

OCR text and Government Resolutions remain subject to their original publication terms. This repo stores code and schema; large corpora and secrets stay local via `.gitignore`.

---

## Phase 3 — Embeddings & pgvector Semantic Search

Phase 3 introduces vector search capability for PostgreSQL, enabling natural language semantic search across Marathi Government Resolutions.

### 1. Prerequisites & Environment Setup

Ensure `pgvector` PostgreSQL extension is available on your database server (`CREATE EXTENSION IF NOT EXISTS vector;` is executed automatically via `Database.ensure_schema()`).

Add vector configuration variables to your `.env` file:

```bash
# Embeddings (Phase 3)
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
EMBEDDING_BATCH_SIZE=32
```

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | Multilingual SentenceTransformer model suitable for Marathi legal text (768-dim) |
| `EMBEDDING_BATCH_SIZE` | `32` | Batch size for model inference and Postgres updates |
| `EMBEDDING_MAX_OCR_CHARS` | `500` | Truncated prefix length of `ocr_text` included in embedding text |

### 2. Generating Embeddings

Run the batch embedding generator:

```bash
python -m embeddings.embed
```

- Pulls documents from PostgreSQL where `embedding IS NULL` (resumable / idempotent).
- Constructs compact text representations via `build_embedding_text()` (`subject_mr` + `department` + `gr_number_canonical` + truncated `ocr_text`).
- Generates 768-dimensional embeddings and updates `gr_documents.embedding`.
- Displays progress via `tqdm` progress bars.

### 3. Querying via Semantic Search

Perform natural language cosine similarity search against `gr_documents`:

```bash
python -m embeddings.search "मुलींसाठी शिष्यवृत्ती"
```

Sample output format:

```text
Executing semantic search for: 'मुलींसाठी शिष्यवृत्ती'

Top 20 results:
============================================================
[01] Score: 0.8412
     ID        : 142
     GR Number : MVR-2023/CR12/PR1
     Dept      : महिला व बालविकास विभाग
     Date      : 2023-05-15
     Subject   : मुलींसाठी विशेष शिष्यवृत्ती योजना मंजुरीबाबत...
     File      : 20230515120000001.txt
------------------------------------------------------------
```

### 4. Python API Usage

```python
from embeddings.search import semantic_search

results = semantic_search("मुलींसाठी शिष्यवृत्ती", top_k=10)
for item in results:
    print(f"[{item['score']:.4f}] {item['gr_number_canonical']} - {item['subject_mr']}")
```

---

## Phase 4 — Graph + Vector Retrieval (Hybrid Search)

Phase 4 combines natural language vector retrieval with citation graph expansion in Neo4j to retrieve both semantically relevant GRs and their directly/indirectly cited dependencies.

```
                  Query
                    │
                    ▼
       ┌────────────────────────┐
       │ pgvector Semantic      │  top_k seed GRs (ranked by similarity score)
       │ Search                 │
       └───────────┬────────────┘
                   │ seed GR IDs
                   ▼
       ┌────────────────────────┐
       │ Neo4j CITES Graph      │  expand paths: (seed)-[:CITES*1..hops]-(related)
       │ Expansion              │  (both directions, excludes seed IDs)
       └───────────┬────────────┘
                   │ union & deduplicate (vector hits prioritized)
                   ▼
       ┌────────────────────────┐
       │ Postgres Batch         │  SELECT metadata WHERE id = ANY(final_ids)
       │ Metadata Hydration     │
       └───────────┬────────────┘
                   │
                   ▼
             Merged Results
```

### 1. Hybrid Pipeline Concept

- **Vector Seeds (`source: "vector"`)**: Retrieved via pgvector cosine similarity search (`embeddings.search.semantic_search`). They retain their numeric similarity score (`score`).
- **Graph Expansion (`source: "graph"`)**: Retrieved by traversing Neo4j `CITES` relationships up to `hops` distance from seed nodes. They carry `hop_distance` (e.g. 1, 2) and `score: None` because graph-expanded nodes are included for structural citation context rather than textual similarity.
- **Deduplication**: Vector hits are prioritized over graph hits (a vector hit will never be overwritten by a graph expansion).
- **Ranking**: Vector seeds appear first in similarity rank order, followed by graph-expanded hits ordered by `hop_distance` ascending.

### 2. Running Hybrid Search via CLI

Run a hybrid search query with default parameters (`top_k=20`, `hops=1`, `max_results=50`):

```bash
python -m retrieval.hybrid "AICTE engineering colleges"
```

Example CLI Output:

```text
Executing hybrid search for: 'AICTE engineering colleges'
Parameters: top_k=20, hops=1, max_results=50

Total results returned: 24

ID       GR Number                           Department                     Source   Hops  Score   
================================================================────────────────────────────────
1405     अकिंरा-2015/प्र.क्र.125/तांशि-4     उच्च व तंत्र शिक्षण विभाग      vector   0     0.7842  
892      सँकिर्ण-2011/प्र.क्र.98/तांशि-4     उच्च व तंत्र शिक्षण विभाग      vector   0     0.7105  
2104     अकिंरा-2018/प्र.क्र.44/तांशि-4      उच्च व तंत्र शिक्षण विभाग      graph    1     N/A     
```

### 3. Python API Usage

```python
from retrieval.hybrid import hybrid_search

results = hybrid_search("AICTE engineering colleges", top_k=10, hops=1, max_results=30)

for res in results:
    score_str = f"{res['score']:.4f}" if res['score'] is not None else "N/A"
    print(f"[{res['source']}|hop={res['hop_distance']}|score={score_str}] "
          f"{res['gr_number_canonical']} - {res['subject_mr']}")
```

---

## Phase 5 — AI Reasoning (RAG over Graph)

Phase 5 builds an LLM reasoning engine on top of Phase 4's hybrid retrieval to support natural language Q&A, pairwise GR comparisons, and draft GR conflict/contradiction detection.

```
 User Query / Draft GR / GR Pair
               │
               ▼
   ┌──────────────────────┐
   │ Hybrid Retrieval     │  vector seeds + graph expansion
   │ (retrieval.hybrid)   │
   └───────────┬──────────┘
               │ candidate GRs
               ▼
   ┌──────────────────────┐
   │ Context Builder      │  selective OCR text hydration &
   │ (reasoning.context)  │  label assignment ([GR 1], [GR 2]...)
   └───────────┬──────────┘
               │ structured context block
               ▼
   ┌──────────────────────┐
   │ Groq LLM Reasoner    │  multi-key rotation, strict system prompts,
   │ (reasoning.llm)      │  JSON format enforcement & retry validation
   └───────────┬──────────┘
               │
               ▼
  Pydantic Validated JSON
 (QueryAnswer / ComparisonResult / ConflictFinding)
```

> [!NOTE]
> **Design Note**: Phase 5 uses Retrieval-Augmented Generation (RAG) over the hybrid citation graph rather than fine-tuned models. All answers are strictly grounded in retrieved GR context to eliminate hallucinated legal claims.

### 1. Configuration Setup

Add reasoning configuration to your `.env` file:

```bash
# AI Reasoning (Phase 5)
REASONING_MODEL=llama-3.3-70b-versatile
REASONING_MAX_FULL_TEXT_DOCS=8
```

| Variable | Default | Description |
|----------|---------|-------------|
| `REASONING_MODEL` | `llama-3.3-70b-versatile` | Strong Groq LLM model for legal reasoning and JSON synthesis |
| `REASONING_MAX_FULL_TEXT_DOCS` | `8` | Max top-priority GRs to include full OCR text excerpts for in prompts |

### 2. CLI Commands & Output Examples

#### Task 1: General Q&A over GR Corpus (`query`)

```bash
python -m reasoning.llm_reasoner query "does GR X conflict with scholarship policy"
```

Example Output (`QueryAnswer` JSON):

```json
{
  "answer": "According to [GR 1] and [GR 2], the revised scholarship policy applies to students enrolled in technical courses. [GR 1] establishes eligibility criteria...",
  "supporting_grs": [
    {
      "label": "[GR 1]",
      "gr_number_canonical": "संकीर्ण2023/प्र.क्र.12/मशि2",
      "relevance_note": "Specifies scholarship eligibility rules."
    }
  ],
  "confidence": 0.95
}
```

#### Task 2: Pairwise GR Comparison (`compare`)

```bash
python -m reasoning.llm_reasoner compare 142 860
```

Example Output (`ComparisonResult` JSON):

```json
{
  "summary": "GR B updates the administrative approval for hostel construction and alters student quota requirements.",
  "added": [
    "1200 seat auditorium allocation for ITI Karad."
  ],
  "removed": [
    "Prior committee approval clause from 2009 policy."
  ],
  "changed": [
    "Land allocation increased from 5000 sq.m to 7000 sq.m."
  ],
  "contradictions": [],
  "confidence": 0.92
}
```

#### Task 3: Draft Conflict Detection (`conflict`)

```bash
python -m reasoning.llm_reasoner conflict "मुलींसाठी विशेष शिष्यवृत्ती योजना मंजुरीबाबत..."
```

Example Output (`ConflictFinding` JSON):

```json
{
  "conflicting": true,
  "explanation": "The proposed draft conflicts with existing policy in [GR 1] regarding income ceiling limits for girls' scholarship eligibility.",
  "conflicting_clauses": [
    "Draft specifies annual family income < ₹8 Lakhs, whereas [GR 1] mandates < ₹2.5 Lakhs."
  ],
  "affected_grs": [
    {
      "label": "[GR 1]",
      "gr_number_canonical": "अर्थसं2022/प्र.क्र.52/मशि3",
      "relevance_note": "Conflicting income ceiling rule."
    }
  ],
  "confidence": 0.89
}
```

---

## Running the API Layer (`backend/api`)

The `api/` package provides a FastAPI layer exposing search, document management, graph visualization, and AI reasoning over HTTP.

### 1. Start the API Server

From the `backend/` directory (or workspace root), run:

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

> [!NOTE]
> Ensure the separate frontend (e.g. React/Vite dev server running on `http://localhost:5173`) has its API base URL environment variable set to:
> `VITE_API_BASE_URL=http://localhost:8000`

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

### 2. API Endpoints Table

| Method | Path | Description / Purpose |
|--------|------|-----------------------|
| `GET` | `/health` | Health check & Postgres database connectivity check |
| `GET` | `/search?q=<query>&top_k=20&hops=1` | Hybrid vector + graph expansion search |
| `GET` | `/search/vector-only?q=<query>&top_k=20` | Plain vector semantic search |
| `GET` | `/documents` | List & paginate GR documents (`page`, `page_size`, `department`, `search`) |
| `GET` | `/documents/{gr_id}` | Detailed metadata + full OCR text + raw JSONB citations |
| `GET` | `/documents/{gr_id}/citations` | Raw citations array & resolved Neo4j target GRs |
| `GET` | `/graph/{gr_id}?hops=2` | Subgraph node/link network for visualizers (`react-force-graph` / `vis-network`) |
| `POST` | `/reasoning/query` | RAG natural language Q&A (`QueryAnswer` JSON) |
| `POST` | `/reasoning/compare` | Pairwise clause comparison (`ComparisonResult` JSON) |
| `POST` | `/reasoning/conflict` | Draft conflict & contradiction detection (`ConflictFinding` JSON) |




