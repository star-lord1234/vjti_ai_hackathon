# Maharashtra GR Intelligence & Draft Analysis

End-to-end system for **Maharashtra Government Resolution (GR) corpus intelligence** and **interactive draft review**: ingest OCR text into PostgreSQL, build a citation graph in Neo4j, run hybrid semantic + graph retrieval, and analyse uploaded drafts through a React web app with conflict detection, template compliance, bilingual terminology checking, and a document-aware chat assistant.

---

## Features

### Corpus build (offline)

```
OCR fulltext (.txt)
        │
        ▼
┌───────────────────┐
│ Rule extractor    │  header metadata (regex, no API)
└─────────┬─────────┘
          │ gaps only
          ▼
┌───────────────────┐
│ Groq LLM backfill │  optional field fill
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ PostgreSQL        │  gr_documents + citations JSONB
└─────────┬─────────┘
          ├──────────────────────┐
          ▼                      ▼
┌───────────────────┐   ┌───────────────────┐
│ pgvector embed    │   │ Citation resolver │  deterministic, no LLM
│ gr_documents +    │   └─────────┬─────────┘
│ gr_chunks         │             ▼
└─────────┬─────────┘   ┌───────────────────┐
          │             │ Neo4j CITES graph │  (:GR)-[:CITES]->(:GR)
          └─────────────┴───────────────────┘
```

### Retrieval & corpus reasoning

```
Natural-language query / GR pair / draft clause seeds
        │
        ▼
┌───────────────────┐
│ Hybrid retrieval  │  pgvector top_k seeds
└─────────┬─────────┘
          │ + Neo4j citation expansion (hops)
          ▼
┌───────────────────┐
│ Context builder   │  OCR excerpts, labels [GR 1]…
└─────────┬─────────┘
          ▼
┌───────────────────┐
│ Groq LLM reasoner │  GROQ_API_KEY_* pool (round-robin)
└─────────┬─────────┘
          │
          ├── query    → QueryAnswer (RAG Q&A)
          ├── compare  → ComparisonResult (pairwise GR diff)
          └── conflict → ConflictFinding (draft vs corpus)
```

### Draft analysis (upload → review)

```
User uploads / pastes draft (TXT or PDF)
        │
        ▼
┌───────────────────┐
│ POST /reasoning/  │  parallel checks, per-section status
│ analyze           │
└─────────┬─────────┘
          │
    ┌─────┼─────┬─────────────┐
    ▼     ▼     ▼             │
┌────────┐ ┌────────┐ ┌──────────────┐
│Conflict│ │Glossary│ │  Template    │
│ LLM +  │ │ LLM +  │ │  rule-based  │
│ hybrid │ │glossary│ │  section     │
│  RAG   │ │  JSON  │ │  order score │
└───┬────┘ └───┬────┘ └──────┬───────┘
    │          │              │
    └──────────┴──────────────┘
               ▼
┌───────────────────────────────────────┐
│ Review UI                             │
│  · document viewer + clause highlight │
│  · Conflicts | Template | Terminology │
│  · template accuracy bar              │
│  · inspector: draft ↔ corpus excerpts│
└───────────────────────────────────────┘
               │
               ▼ (anytime, isolated key)
┌───────────────────────────────────────┐
│ Draft chat (POST /chat/message)       │
│  GROQ_CHAT_API_KEY only — not shared  │
│  with analysis pool                   │
└───────────────────────────────────────┘
```

### Platform & ops

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ FastAPI     │────▶│ React +     │────▶│ GET /health │
│ /docs       │     │ Vite UI     │     │ store sync  │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                        │
       ▼                                        ▼
┌─────────────┐                         ┌─────────────┐
│ pytest      │                         │ Makefile    │
│ test-unit   │                         │ eval targets│
└─────────────┘                         └─────────────┘
```

---

## Tech stack

| Layer | Technologies |
|-------|----------------|
| **Backend** | Python 3.10+, FastAPI, Uvicorn, Pydantic v2 |
| **LLM** | Groq API (`llama-3.3-70b-versatile` for analysis; `llama-3.1-8b-instant` for chat / ingest backfill) |
| **Database** | PostgreSQL 14+ with **pgvector** |
| **Graph** | Neo4j 5+ (Bolt) |
| **Embeddings** | `sentence-transformers` (multilingual MPNet, 768-dim) |
| **Frontend** | React 18, TypeScript, Vite 6, Tailwind CSS 4, Lucide icons |
| **PDF** | `pdfjs-dist` (client-side text extraction) |
| **Tooling** | pytest, Make targets for tests and retrieval eval |

---

## Data pipeline (ingest → graph)

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
│ PostgreSQL        │  source of truth (metadata + OCR + vectors)
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
- Optional chunk embeddings into **`gr_chunks`** during ingest.

### 3. Citation resolution
- **`graph/reference_resolver.py`** reads citations from Postgres, extracts a GR number, normalizes it via **`parser/normalize.py`**, and matches `gr_number_canonical`.
- Output: unique `(source_id, target_id)` edges. Unmatched citations are ignored (no hallucinated links).

### 4. Neo4j graph load
- **`graph/neo4j_loader.py`** creates `:GR` nodes and `CITES` relationships with `MERGE` (idempotent).
- Node properties: `id`, `filename`, `gr_number`, `canonical_gr`, `department`, `date`, `subject`.

### 5. Draft analysis (web app)
- **`POST /reasoning/analyze`** — parallel conflict + glossary + template checks on uploaded draft text.
- **`reasoning/llm_reasoner.py`** — conflict / query / compare via shared multi-key `APIManager`.
- **`reasoning/glossary/`** — isolated terminology prompt + `backend/data/glossary.json`.
- **`reasoning/template/`** + **`parser/section_locator.py`** — rule-based GR structure scoring (`backend/data/gr_template_structure.json`).
- **`chat/`** — document-aware assistant on **`GROQ_CHAT_API_KEY` only** (never the analysis pool).

---

## Repository layout

```
vjti/
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI app
│   │   └── routes/              # search, documents, graph, reasoning, chat
│   ├── chat/                    # Isolated draft chatbot (GROQ_CHAT_API_KEY)
│   ├── data/
│   │   ├── glossary.json        # Bilingual terminology seed list
│   │   └── gr_template_structure.json
│   ├── database/
│   │   ├── db.py
│   │   ├── schema.sql
│   │   └── sync_status.py
│   ├── embeddings/
│   │   ├── embed.py
│   │   └── search.py
│   ├── graph/
│   │   ├── reference_resolver.py
│   │   ├── neo4j_loader.py
│   │   └── neo4j_query.py
│   ├── parser/
│   │   ├── rule_extractor.py
│   │   ├── section_patterns.py  # Shared regex for template + rules
│   │   ├── section_locator.py   # Position-aware section detection
│   │   └── normalize.py
│   ├── reasoning/
│   │   ├── llm_reasoner.py      # Conflict / query / compare
│   │   ├── glossary/            # Terminology checker
│   │   ├── template/            # Structure compliance checker
│   │   ├── context_builder.py
│   │   ├── retrieval_gate.py
│   │   └── models.py
│   ├── retrieval/
│   │   └── hybrid.py
│   ├── scripts/
│   │   ├── api_manager.py       # Groq multi-key pool (analysis only)
│   │   ├── extract_metadata.py
│   │   └── ingest.py
│   └── tests/
├── frontend/
│   └── src/
│       ├── app/App.tsx            # Main UI (upload, review, findings)
│       ├── app/components/      # DraftChatWidget, ui/, figma/
│       └── lib/                   # api.ts, adapters.ts, pdf.ts
├── maha_grs 2/maha_grs/fulltext/  # OCR .txt inputs (local / not in git)
├── metadata/                      # Generated JSON (local / not in git)
├── Makefile
├── .env.example
└── README.md
```

---

## Prerequisites

| Tool | Notes |
|------|--------|
| Python 3.10+ | Developed with 3.14 locally |
| Node.js 18+ | For Vite frontend |
| PostgreSQL 14+ | With `pgvector` extension |
| Neo4j 5+ | Neo4j Desktop or local server |
| Groq API keys | Analysis pool (`GROQ_API_KEY_*`) + optional dedicated chat key |

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
pip install -r backend/requirements.txt
```

### 2. Environment file

```bash
cp .env.example backend/.env
```

Edit `backend/.env`:

```bash
# Groq — analysis pool (round-robin, shared by conflict/glossary/query/compare)
GROQ_API_KEY_1=gsk_...
GROQ_API_KEY_2=          # optional extras
GROQ_API_KEY_3=

# Groq — chat only (isolated; never mixed into analysis pool)
GROQ_CHAT_API_KEY=gsk_...
GROQ_CHAT_MODEL=llama-3.1-8b-instant

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

# Frontend CORS
FRONTEND_ORIGIN=http://localhost:5173
```

**Never commit `.env`.** It is listed in `.gitignore`.

### 3. PostgreSQL setup

```bash
createdb maha_gr
```

Schema is applied automatically on first `Database()` connect (`database/schema.sql` + migrations in `db.py`).

### 4. Neo4j setup (Desktop)

1. Install [Neo4j Desktop](https://neo4j.com/download/).
2. Create / start a local DBMS; set password in `.env`.
3. Start the DBMS before running `neo4j_loader` or the API.

### 5. Put OCR files in place

```text
maha_grs 2/maha_grs/fulltext/*.txt
```

### 6. Extract metadata → JSON

```bash
cd backend
python scripts/extract_metadata.py
```

### 7. Ingest into PostgreSQL (+ optional embed / Neo4j sync)

```bash
cd backend
INGEST_RUN_EMBED=true INGEST_SYNC_NEO4J=true python scripts/ingest.py
```

### 8. Resolve citations & load Neo4j

```bash
cd backend
python -m graph.reference_resolver
python -m graph.neo4j_loader
```

### 9. Start backend API

```bash
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs: `http://localhost:8000/docs`

### 10. Start frontend

```bash
cd frontend
npm install
npm run dev
```

Set in `frontend/.env` (or rely on default):

```bash
VITE_API_BASE_URL=http://localhost:8000
```

Open `http://localhost:5173` — upload or paste a draft to run analysis.

### 11. Run tests

```bash
make test-unit
```

---

## Viewing the graph

### Neo4j Browser

```cypher
MATCH (a:GR)-[r:CITES]->(b:GR)
RETURN a, r, b
LIMIT 25
```

### Neo4j Bloom

Search `GR CITES GR` or run the same Cypher; set node captions to `gr_number` or `filename`.

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
| `embedding` | pgvector document embedding |

Chunk table **`gr_chunks`** stores clause-level embeddings for finer hybrid retrieval.

---

## Public Python APIs (useful snippets)

```python
from parser.rule_extractor import rule_extract
from retrieval.hybrid import hybrid_search
from reasoning.llm_reasoner import check_conflict, answer_query
from reasoning.glossary import run_glossary_check
from reasoning.template import run_template_check
from chat import handle_chat_message, ChatMessageRequest

# Hybrid search
results, meta = hybrid_search("scholarship policy", top_k=15, hops=1, return_meta=True)

# Draft checks
conflict = check_conflict(draft_input="...")
glossary = run_glossary_check(draft_text="...")
template = run_template_check(draft_text="...")

# Chat (isolated key)
reply = handle_chat_message(ChatMessageRequest(message="...", draft_text="..."))
```

---

## Design notes

- **Postgres is source of truth**; Neo4j is a disposable projection.
- **No LLM in citation resolution** — only regex + `normalize.py`.
- **Analysis vs chat API keys are isolated** — `GROQ_API_KEY_*` pool for conflict/glossary/query/compare; `GROQ_CHAT_API_KEY` for the draft assistant only.
- **Glossary degrades gracefully** — returns `status: unavailable` when analysis keys are exhausted instead of failing the whole analyse response.
- **Template checking is deterministic** — no LLM; shared section patterns with `rule_extractor`.
- **Idempotent Neo4j load** via `MERGE` on node `id` and `CITES` edges.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `No Groq API keys found` | Set `GROQ_API_KEY_1` in `backend/.env` |
| Chat unavailable | Set `GROQ_CHAT_API_KEY`; check Groq dashboard quota for that key |
| Glossary unavailable but conflict works | Analysis keys on cooldown — glossary fails fast by design |
| Postgres connection errors | Check `POSTGRES_*` in `.env`; ensure `maha_gr` exists |
| Neo4j `ServiceUnavailable` | Start the DBMS in Desktop |
| Frontend can't reach API | Set `VITE_API_BASE_URL`; check CORS `FRONTEND_ORIGIN` |
| Groq 413 / token limit on conflict | Lower `GROQ_MAX_INPUT_TOKENS` or draft size; restart uvicorn after `.env` changes |
| LLM ingest phase paused | Free-tier quotas; re-run later — JSON resume is supported |

---

## License / data

OCR text and Government Resolutions remain subject to their original publication terms. This repo stores code and schema; large corpora and secrets stay local via `.gitignore`.

---

## Phase 3 — Embeddings & pgvector Semantic Search

Phase 3 introduces vector search capability for PostgreSQL, enabling natural language semantic search across Marathi Government Resolutions.

### 1. Prerequisites & Environment Setup

Ensure `pgvector` PostgreSQL extension is available (`CREATE EXTENSION IF NOT EXISTS vector;` is executed automatically via `Database.ensure_schema()`).

```bash
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
EMBEDDING_BATCH_SIZE=32
```

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `paraphrase-multilingual-mpnet-base-v2` | Multilingual SentenceTransformer (768-dim) |
| `EMBEDDING_BATCH_SIZE` | `32` | Batch size for inference |
| `EMBEDDING_MAX_OCR_CHARS` | `500` | OCR prefix in embedding text |

### 2. Generating Embeddings

```bash
cd backend && python -m embeddings.embed
```

### 3. Querying via Semantic Search

```bash
cd backend && python -m embeddings.search "मुलींसाठी शिष्यवृत्ती"
```

### 4. Python API Usage

```python
from embeddings.search import semantic_search

results = semantic_search("मुलींसाठी शिष्यवृत्ती", top_k=10)
```

---

## Phase 4 — Graph + Vector Retrieval (Hybrid Search)

Phase 4 combines natural language vector retrieval with citation graph expansion in Neo4j.

```
                  Query
                    │
                    ▼
       ┌────────────────────────┐
       │ pgvector Semantic      │  top_k seed GRs
       │ Search                 │
       └───────────┬────────────┘
                   ▼
       ┌────────────────────────┐
       │ Neo4j CITES Graph      │  expand (seed)-[:CITES*1..hops]-(related)
       │ Expansion              │
       └───────────┬────────────┘
                   ▼
       ┌────────────────────────┐
       │ Postgres Hydration     │
       └───────────┬────────────┘
                   ▼
             Merged Results
```

### CLI

```bash
cd backend && python -m retrieval.hybrid "AICTE engineering colleges"
```

### Python API

```python
from retrieval.hybrid import hybrid_search

results = hybrid_search("AICTE engineering colleges", top_k=10, hops=1)
```

---

## Phase 5 — AI Reasoning (RAG over Graph)

Phase 5 builds an LLM reasoning engine on top of hybrid retrieval for Q&A, pairwise comparison, and draft conflict detection.

```
 User Query / Draft GR / GR Pair
               │
               ▼
   ┌──────────────────────┐
   │ Hybrid Retrieval     │
   └───────────┬──────────┘
               ▼
   ┌──────────────────────┐
   │ Context Builder      │
   └───────────┬──────────┘
               ▼
   ┌──────────────────────┐
   │ Groq LLM Reasoner    │  GROQ_API_KEY_* pool + cooldowns
   └───────────┬──────────┘
               ▼
  Pydantic Validated JSON
```

> **Design note:** RAG over the hybrid citation graph — answers grounded in retrieved GR context.

### Configuration

```bash
REASONING_MODEL=llama-3.3-70b-versatile
GROQ_MAX_INPUT_TOKENS=9000
CONFLICT_TOP_K=10
```

### CLI examples

```bash
cd backend
python -m reasoning.llm_reasoner query "scholarship eligibility"
python -m reasoning.llm_reasoner compare 142 860
python -m reasoning.llm_reasoner conflict "draft text here..."
```

---

## Phase 6 — Draft Analysis Suite (Glossary + Template)

Extends Phase 5 with additional draft checks, exposed individually and via **`POST /reasoning/analyze`**.

| Check | Module | LLM? | Notes |
|-------|--------|------|-------|
| **Conflict** | `reasoning/llm_reasoner.py` | Yes | Shared `GROQ_API_KEY_*` pool |
| **Glossary** | `reasoning/glossary/` | Yes | Separate prompt; same key pool; fail-fast on exhaustion |
| **Template** | `reasoning/template/` | No | Rule-based; `gr_template_structure.json` + `section_locator.py` |

**Template accuracy scoring:** weighted score over required sections — full credit if present and in order, half credit if misordered, zero if missing.

**Glossary:** seeded terms in `backend/data/glossary.json` (~50 entries); only flags glossary-listed variants.

---

## Phase 7 — Web UI & Draft Chat

### Frontend workflow

1. **Upload** TXT/PDF or paste draft text.
2. **Processing** — calls `POST /reasoning/analyze`.
3. **Review** — document viewer + tabs: **Conflicts** | **Template** | **Terminology**.
4. **Chat** — floating assistant (bottom-right) using `POST /chat/message`.

### Chat isolation

- Uses **`GROQ_CHAT_API_KEY`** only — dedicated `Groq` client in `backend/chat/service.py`.
- Never imports `APIManager` or analysis reasoner paths.
- Stateless: each request includes `draft_text`, `message`, and client-side `history`.
- Per-session in-memory rate limit (default 20 messages/minute).

---

## Running the API Layer (`backend/api`)

```bash
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend: `VITE_API_BASE_URL=http://localhost:8000`

Interactive docs: `http://localhost:8000/docs`

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Postgres, Neo4j, embeddings, store-sync health |
| `GET` | `/search?q=...&top_k=20&hops=1` | Hybrid vector + graph search |
| `GET` | `/search/vector-only?q=...` | Vector-only semantic search |
| `GET` | `/documents` | Paginated GR list |
| `GET` | `/documents/{gr_id}` | Full metadata + OCR |
| `GET` | `/documents/{gr_id}/citations` | Citations + resolved targets |
| `GET` | `/graph/{gr_id}?hops=2` | Citation subgraph for visualization |
| `POST` | `/reasoning/query` | RAG Q&A (`QueryAnswer`) |
| `POST` | `/reasoning/compare` | Pairwise GR comparison |
| `POST` | `/reasoning/conflict` | Draft conflict detection |
| `POST` | `/reasoning/glossary` | Terminology check only |
| `POST` | `/reasoning/analyze` | Parallel conflict + glossary + template |
| `POST` | `/chat/message` | Document-aware draft chat (isolated key) |

### Analyse response shape (partial success)

```json
{
  "conflict_check": { "status": "ok", "result": { "...ConflictFinding" } },
  "glossary_check": { "status": "ok", "findings": [] },
  "template_check": { "status": "ok", "accuracy_score": 85.0, "findings": [], "violations": [] }
}
```

`glossary_check.status` may be `"unavailable"` with `"reason": "api_quota_exhausted"` while conflict still succeeds.

### Chat response shape

```json
{ "status": "ok", "reply": "..." }
```

Or `{ "status": "unavailable", "reason": "api_quota_exhausted" }` / `{ "status": "no_document" }` / `{ "status": "error" }`.

