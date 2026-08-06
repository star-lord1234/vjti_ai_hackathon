# Maharashtra GR Intelligence & Draft Analysis

End-to-end system for **Maharashtra Government Resolution (GR) corpus intelligence** and **interactive draft review**: ingest OCR text into PostgreSQL, build a citation graph in Neo4j, run hybrid semantic + graph retrieval, and analyse uploaded drafts through a React web app with conflict detection, template compliance, bilingual terminology checking, and a document-aware chat assistant.

Designed for local-only deployment: embeddings, reasoning, draft analysis, and chat can all run fully offline once models and data are available.

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
│ Ollama LLM backfill │  optional field fill
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
│ Ollama LLM reasoner │  local llama3.1 via LLMClientManager
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
               ▼ (anytime, isolated client)
┌───────────────────────────────────────┐
│ Draft chat (POST /chat/message)       │
│  separate Ollama client — not shared  │
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

| Layer          | Technologies                                                                             |
| -------------- | ---------------------------------------------------------------------------------------- |
| **Backend**    | Python 3.10+, FastAPI, Uvicorn, Pydantic v2                                              |
| **LLM**        | Local [Ollama](https://ollama.com/) (`llama3.1` for analysis, chat, and ingest backfill) |
| **Database**   | PostgreSQL 14+ with **pgvector**                                                         |
| **Graph**      | Neo4j 5+ (Bolt)                                                                          |
| **Embeddings** | `sentence-transformers` (multilingual MPNet, 768-dim)                                    |
| **Frontend**   | React 18, TypeScript, Vite 6, Tailwind CSS 4, Lucide icons                               |
| **PDF**        | `pdfjs-dist` (client-side text extraction)                                               |
| **Tooling**    | pytest, Make targets for tests and retrieval eval                                        |

---

## External sources

Third-party models and data used by this project. Self-hosted stores (PostgreSQL, Neo4j) are not listed here.

### LLM (Ollama — local inference)

All LLM calls go through a **local Ollama** server. Default model: **`llama3.1`**. Fully offline capable with no cloud API keys required.

| Model tag  | Env var             | Used for                                                                  |
| ---------- | ------------------- | ------------------------------------------------------------------------- |
| `llama3.1` | `REASONING_MODEL`   | Conflict detection, glossary terminology check, corpus Q&A, GR comparison |
| `llama3.1` | `INGEST_LLM_MODEL`  | Ingest metadata backfill when rule extraction leaves gaps                 |
| `llama3.1` | `OLLAMA_CHAT_MODEL` | Draft chat assistant (`POST /chat/message`)                               |

**Client separation**

| Client          | Module                                | Notes                              |
| --------------- | ------------------------------------- | ---------------------------------- |
| Analysis pool   | `llm/manager.py` (`LLMClientManager`) | Conflict, glossary, query, compare |
| Chat (isolated) | `backend/chat/service.py`             | Separate Ollama client instance    |

Configure via `OLLAMA_BASE_URL` (default `http://localhost:11434/v1`) and `OLLAMA_MODEL`.

Template/structure checking is **rule-based** and does not call any LLM.

### Embedding model (Hugging Face — local inference)

| Model                                                                                                                                               | Env var           | Notes                                                                                                          |
| --------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------- |
| [`sentence-transformers/paraphrase-multilingual-mpnet-base-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-mpnet-base-v2) | `EMBEDDING_MODEL` | Downloaded on first run; 768-dim vectors; runs locally via `sentence-transformers` (no external embedding API) |

### Datasets & reference data

| Source                        | Location                                                 | In git? | Description                                                                                                                                                                                                                                    |
| ----------------------------- | -------------------------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Maharashtra GR OCR corpus** | `backend/maha_grs/fulltext/*.txt` (or `GR_FULLTEXT_DIR`) | No      | ~8,250 Government Resolution fulltext files. Original PDFs from the [Maharashtra GR portal](https://gr.maharashtra.gov.in/); OCR text with Marathi (`mr`) primary. Manifest with `source_url` per document: `backend/maha_grs/manifest.jsonl`. |
| **Ingest metadata**           | `metadata/*.json`                                        | No      | Rule/LLM-extracted fields per GR (generated by `extract_metadata.py` / `ingest.py`).                                                                                                                                                           |
| **Terminology glossary**      | `backend/data/glossary.json`                             | Yes     | ~50 bilingual Marathi/English GR terms and variants — project-maintained seed list for the glossary checker.                                                                                                                                   |
| **GR template structure**     | `backend/data/gr_template_structure.json`                | Yes     | Expected section order and headings for Maharashtra GR drafts — project-maintained rules for the template checker.                                                                                                                             |

**Not used:** no external training datasets, no RAG over third-party legal corpora beyond the Maharashtra GR fulltext above, and no cloud vector DB SaaS (vectors live in local PostgreSQL + pgvector).

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
│ Ollama LLM backfill │  optional; skipped when rules succeed
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

End-to-end **Maharashtra GR intelligence and draft review** — from corpus ingest through hybrid search, local LLM reasoning, and an officer-facing web UI with explicit save, versioning, and audit.

### 1. Hybrid metadata extraction

- **`parser/rule_extractor.py`** — extracts `document_type`, `department`, `gr_number`, `date`, `subject`, and `references` (वाचा / संदर्भ) from the document header using regex only.
- **`scripts/extract_metadata.py`** — two-phase runner:
  - **Phase 1:** parallel rule extraction; writes a JSON for every file under `metadata/`.
  - **Phase 2:** Ollama LLM fills only missing fields (paced to avoid overloading local inference).
- Also writes **`gr_normalised`** (uniform GR number) into each JSON.
- On this corpus (~6076 files), rules alone complete most documents; LLM is only for gaps.

### 2. PostgreSQL ingest & embeddings

- **`scripts/ingest.py`** + **`database/db.py`** upsert each JSON plus the matching OCR file into `gr_documents`.
- Full OCR text lives in column **`ocr_text`** (not copied into Neo4j).
- **`embeddings/embed.py`** — document-level and clause-level vectors in **`gr_documents.embedding`** and **`gr_chunks`** (768-dim multilingual MPNet).
- **`embeddings/search.py`** — pgvector cosine nearest-neighbour search over corpus GRs.

### 3. Citation resolution & Neo4j graph

- **`graph/reference_resolver.py`** reads citations from Postgres, extracts a GR number, normalizes it via **`parser/normalize.py`**, and matches `gr_number_canonical`.
- Output: unique `(source_id, target_id)` edges. Unmatched citations are ignored (no hallucinated links).
- **`graph/neo4j_loader.py`** creates `:GR` nodes and `CITES` relationships with `MERGE` (idempotent).
- **`retrieval/hybrid.py`** — vector top_k seeds + Neo4j citation expansion (hops) for richer retrieval context.

### 4. Offline deployment with Ollama (no cloud APIs)

- **All LLM inference runs locally** via [Ollama](https://ollama.com/) (`llama3.1` by default) — conflict detection, optional glossary LLM pass, corpus Q&A, GR comparison, ingest metadata backfill, and draft chat.
- **`llm/client.py`** — lightweight httpx client to Ollama's OpenAI-compatible API (no `openai` package, no API keys).
- **`llm/manager.py`** — shared analysis client pool for conflict / query / compare.
- **`chat/service.py`** — **isolated** Ollama client for the draft assistant (never mixed with the analysis pool).
- **`EMBEDDING_LOCAL_FILES_ONLY=true`** — sentence-transformers loads from local cache so conflict detection works **without WiFi** after the embedding model is cached once.
- Postgres + Neo4j + Ollama on the same machine = fully **air-gapped** operation once corpus and models are in place.

### 5. Hybrid retrieval & corpus reasoning

- **`POST /search`** — hybrid vector + graph search over ~8,000 GRs.
- **`POST /reasoning/query`** — RAG Q&A grounded in retrieved GR context (`QueryAnswer` with supporting GR citations).
- **`POST /reasoning/compare`** — pairwise clause-level comparison and contradiction detection between two corpus GRs.
- **`reasoning/context_builder.py`** + **`reasoning/retrieval_gate.py`** — OCR excerpts, temporal ordering, draft-overlap reranking, and pre-LLM quality gating.

### 6. Conflict detection (draft vs corpus)

- **`POST /reasoning/conflict`** and the conflict leg of **`POST /reasoning/analyze`**.
- **`reasoning/llm_reasoner.py` → `check_conflict()`** — embeds draft clauses, hybrid-searches related corpus GRs, builds a Marathi/English prompt with rule signals and clause excerpts, then asks Ollama for a structured **`ConflictFinding`** (conflicting clauses, affected GRs, corpus excerpts, confidence).
- Surfaces conflicts, duplications, supersession, and cross-departmental issues in the review UI with clause highlighting.

### 7. Template compliance (rule-based, no LLM)

- **`POST /reasoning/template`** and the template leg of **`POST /reasoning/analyze`**.
- **`reasoning/template/`** + **`parser/section_locator.py`** — checks draft structure against **`backend/data/gr_template_structure.json`** (header, subject, preamble, operative section, financial sanction, budget head, signatory, etc.).
- Weighted **accuracy score** over required sections; flags missing or misordered sections with severity (high / medium / low).
- Instant — no network or LLM round-trip.

### 8. Bilingual terminology / glossary checking

- **`POST /reasoning/glossary`** and the glossary leg of **`POST /reasoning/analyze`**.
- **`reasoning/glossary/`** + **`backend/data/glossary.json`** (~50 seeded Marathi/English GR terms and variants).
- **Default: deterministic rule-based scan** (`GLOSSARY_USE_LLM=false`) — flags non-canonical glossary variants instantly with context snippets and confidence scores.
- **Optional LLM pass** (`GLOSSARY_USE_LLM=true`) for deeper terminology review via Ollama when enabled.
- Degrades gracefully (`status: unavailable`) if the LLM client is on cooldown — does not fail the whole analyse response.

### 9. Combined draft analysis (`POST /reasoning/analyze`)

- Runs **conflict + glossary + template** in one request; returns per-section status so partial success is supported (e.g. conflict OK, glossary unavailable).
- Accepts optional **`gr_document_id`** and **`actor`** — when set, writes an **`ai_suggestion`** row to **`audit_log`** with the full finding snapshot.
- Frontend **Processing** phase calls this on upload; results populate the **Conflicts**, **Template**, and **Terminology** review tabs.

### 10. Editable drafts, versioning & audit trail

- **`POST /drafts`** — create a persisted editable draft (`gr_documents` row + `gr_versions` v1).
- **`POST /drafts/{id}/save`** — explicit save with deterministic template + glossary checks; **`human_edit`** audit row (with unified diff) when text changes.
- **`POST /drafts/{id}/save-and-recheck`** — save + full conflict LLM recheck; promotes status to **`ready_for_approval`** when zero high-severity findings remain.
- **`audit_log`** — centralized via **`services/audit.py` → `log_action()`**; records `human_edit`, `ai_suggestion`, `submitted_for_review`, actor, diff, and JSON finding snapshots.
- **`gr_versions`** — full-text version history; **no duplicate version** when text is unchanged between saves.
- **`gr_documents.status`** — `draft` · `ready_for_approval` · `approved`.
- Frontend: editable textarea (no auto-save), **Save Draft** / **Save & Recheck** buttons, status badge, version indicator, unsaved-changes flag, preview mode with finding highlights.

### 11. Document-aware draft chat

- **`POST /chat/message`** — floating assistant in the review UI.
- **`chat/service.py`** — answers questions about the current draft using retrieved corpus context; runs on a **dedicated local Ollama client**.
- Stateless per request (`draft_text`, `message`, `history`); per-session rate limit.

### 12. Web UI, health & operations

- **React + Vite** app — upload TXT/PDF or paste draft, processing pipeline animation, three-panel review (document + findings + inspector), export, sample draft loader.
- **`GET /health`** — Postgres, Neo4j, embedding coverage, and store-sync drift warnings.
- **`database/sync_status.py`** — detects corpus/embedding/graph mismatches; excludes editable `draft-*` rows from embedding drift checks.
- **pytest** unit tests (`make test-unit`); OpenAPI docs at `/docs`.

---

## Repository layout

```
vjti/
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI app
│   │   └── routes/              # search, documents, graph, reasoning, chat
│   ├── chat/                    # Isolated draft chatbot (local Ollama)
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
│   │   ├── llm/manager.py       # Local Ollama client manager (analysis)
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

| Tool           | Notes                                                     |
| -------------- | --------------------------------------------------------- |
| Python 3.10+   | Developed with 3.14 locally                               |
| Node.js 18+    | For Vite frontend                                         |
| PostgreSQL 14+ | With `pgvector` extension                                 |
| Neo4j 5+       | Neo4j Desktop or local server                             |
| Ollama         | Running locally (`ollama serve`); model `llama3.1` pulled |

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
# Ollama — local LLM (conflict/glossary/query/compare + ingest backfill)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=llama3.1
REASONING_MODEL=llama3.1
INGEST_LLM_MODEL=llama3.1

# Chat — isolated Ollama client (never mixed into analysis pool)
OLLAMA_CHAT_MODEL=llama3.1

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

| Column                               | Purpose                               |
| ------------------------------------ | ------------------------------------- |
| `id`                                 | Primary key (used as Neo4j node `id`) |
| `filename`                           | Unique OCR filename                   |
| `document_type` / `document_type_en` | e.g. शासन निर्णय                      |
| `department`                         | Issuing department                    |
| `gr_number_original`                 | As extracted                          |
| `gr_number_normalized`               | Digits/spacing cleaned                |
| `gr_number_canonical`                | Match key for citations               |
| `gr_date`                            | Issue date                            |
| `subject_mr`                         | Subject                               |
| `citations`                          | JSONB array of `{raw, date}`          |
| `ocr_text`                           | Full OCR (Postgres only)              |
| `embedding`                          | pgvector document embedding           |

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
- **Analysis vs chat clients are isolated** — `LLMClientManager` for conflict/glossary/query/compare; separate Ollama client in `chat/service.py` for the draft assistant.
- **Glossary degrades gracefully** — returns `status: unavailable` when the LLM client is cooling down instead of failing the whole analyse response.
- **Template checking is deterministic** — no LLM; shared section patterns with `rule_extractor`.
- **Idempotent Neo4j load** via `MERGE` on node `id` and `CITES` edges.

---

## Troubleshooting

| Issue                                   | Fix                                                                                                                                          |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `Connection refused` on LLM calls       | Start Ollama: `ollama serve`; verify `OLLAMA_BASE_URL` in `backend/.env`                                                                     |
| Chat unavailable                        | Ensure Ollama is running; run `ollama list` and confirm `llama3.1` is present                                                                |
| Glossary unavailable but conflict works | LLM client on cooldown — glossary fails fast by design                                                                                       |
| Postgres connection errors              | Check `POSTGRES_*` in `.env`; ensure `maha_gr` exists                                                                                        |
| Neo4j `ServiceUnavailable`              | Start the DBMS in Desktop                                                                                                                    |
| Frontend can't reach API                | Set `VITE_API_BASE_URL`; check CORS `FRONTEND_ORIGIN`                                                                                        |
| Context / token limit on conflict       | Lower `LLM_MAX_INPUT_TOKENS` or draft size; restart uvicorn after `.env` changes                                                             |
| Conflict fails when WiFi is off         | Ensure `EMBEDDING_LOCAL_FILES_ONLY=true`; run `python -m embeddings.embed` once while online to cache the model; keep `ollama serve` running |
| LLM ingest phase paused                 | Ollama overloaded or down; re-run later — JSON resume is supported                                                                           |

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

| Variable                  | Default                                 | Description                                |
| ------------------------- | --------------------------------------- | ------------------------------------------ |
| `EMBEDDING_MODEL`         | `paraphrase-multilingual-mpnet-base-v2` | Multilingual SentenceTransformer (768-dim) |
| `EMBEDDING_BATCH_SIZE`    | `32`                                    | Batch size for inference                   |
| `EMBEDDING_MAX_OCR_CHARS` | `500`                                   | OCR prefix in embedding text               |

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
   │ Ollama LLM Reasoner    │  local llama3.1 + cooldowns
   └───────────┬──────────┘
               ▼
  Pydantic Validated JSON
```

> **Design note:** RAG over the hybrid citation graph — answers grounded in retrieved GR context.

### Configuration

```bash
REASONING_MODEL=llama-3.3-70b-versatile
LLM_MAX_INPUT_TOKENS=9000
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

| Check        | Module                      | LLM? | Notes                                                           |
| ------------ | --------------------------- | ---- | --------------------------------------------------------------- |
| **Conflict** | `reasoning/llm_reasoner.py` | Yes  | Shared `LLMClientManager`                                       |
| **Glossary** | `reasoning/glossary/`       | Yes  | Separate prompt; same key pool; fail-fast on exhaustion         |
| **Template** | `reasoning/template/`       | No   | Rule-based; `gr_template_structure.json` + `section_locator.py` |

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

- Uses a **dedicated local Ollama client** in `backend/chat/service.py`.
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

| Method | Path                                  | Description                                              |
| ------ | ------------------------------------- | -------------------------------------------------------- |
| `GET`  | `/health`                             | Postgres, Neo4j, embeddings, store-sync health           |
| `GET`  | `/search?q=...&top_k=20&hops=1`       | Hybrid vector + graph search                             |
| `GET`  | `/search/vector-only?q=...`           | Vector-only semantic search                              |
| `GET`  | `/documents`                          | Paginated GR list                                        |
| `GET`  | `/documents/{gr_id}`                  | Full metadata + OCR                                      |
| `GET`  | `/documents/{gr_id}/citations`        | Citations + resolved targets                             |
| `GET`  | `/graph/{gr_id}?hops=2`               | Citation subgraph for visualization                      |
| `POST` | `/reasoning/query`                    | RAG Q&A (`QueryAnswer`)                                  |
| `POST` | `/reasoning/compare`                  | Pairwise GR comparison                                   |
| `POST` | `/reasoning/conflict`                 | Draft conflict detection                                 |
| `POST` | `/reasoning/glossary`                 | Terminology check only                                   |
| `POST` | `/reasoning/template`                 | Rule-based GR template compliance                        |
| `POST` | `/reasoning/analyze`                  | Parallel conflict + glossary + template                  |
| `POST` | `/drafts`                             | Create a new editable draft                              |
| `GET`  | `/drafts/{draft_id}`                  | Fetch saved draft summary and text                       |
| `POST` | `/drafts/{draft_id}/save`             | Save draft with deterministic checks                     |
| `POST` | `/drafts/{draft_id}/save-and-recheck` | Save draft and run conflict + glossary + template checks |
| `POST` | `/chat/message`                       | Document-aware draft chat (isolated key)                 |

### Analyse response shape (partial success)

```json
{
  "conflict_check": { "status": "ok", "result": { "...ConflictFinding" } },
  "glossary_check": { "status": "ok", "findings": [] },
  "template_check": { "status": "ok", "accuracy_score": 85.0, "findings": [], "violations": [] }
}
```

`glossary_check.status` may be `"unavailable"` with `"reason": "llm_unavailable"` while conflict still succeeds.

### Chat response shape

```json
{ "status": "ok", "reply": "..." }
```

Or `{ "status": "unavailable", "reason": "llm_unavailable" }` / `{ "status": "no_document" }` / `{ "status": "error" }`.

---

## Phase 8 — Editable Drafts, Versioning & Audit Trail

This phase adds a persisted draft workflow on top of the existing analyse UI: officers edit draft text explicitly, save versions, re-run checks, and every action is recorded in Postgres.

### What was added

| Area            | Capability                                                                                          |
| --------------- | --------------------------------------------------------------------------------------------------- |
| **Database**    | `audit_log`, `gr_versions`, and `gr_documents.status` (`draft` · `ready_for_approval` · `approved`) |
| **Backend**     | `services/audit.py` — single `log_action()` helper (no scattered INSERTs)                           |
| **Backend**     | `services/draft.py` — save, save-and-recheck, diff computation, status transitions                  |
| **API**         | `POST /drafts`, `GET /drafts/{id}`, `POST /drafts/{id}/save`, `POST /drafts/{id}/save-and-recheck`  |
| **API**         | `POST /reasoning/analyze` accepts optional `gr_document_id` + `actor` to log initial analysis       |
| **Frontend**    | Editable textarea in review phase (no auto-save); **Save Draft** and **Save & Recheck** buttons     |
| **Frontend**    | Status badge, version indicator, and “unsaved changes” dirty state                                  |
| **Offline**     | `EMBEDDING_LOCAL_FILES_ONLY=true`; Ollama via httpx (`llm/client.py`, no `openai` package)          |
| **Glossary**    | Deterministic rule-based scan by default (`GLOSSARY_USE_LLM=false`) for instant terminology checks  |
| **Reliability** | Schema migrations run once per process (avoids Postgres deadlocks during parallel analyse)          |

Editable officer drafts are stored as `gr_documents` rows with filenames like `draft-<uuid>-<name>.txt`. They are **excluded from corpus embedding drift checks** in `/health` (they are working copies, not retrieval targets).

### Draft status lifecycle

```
draft  ──(Save & Recheck, zero high-severity findings)──▶  ready_for_approval  ──▶  approved
  ▲                                                          │
  └──────────────── issues remain ───────────────────────────┘
```

**Save & Recheck** implies a save when text changed; it does not require a prior **Save Draft** click.

### Audit log events

| `action_type`          | When                                                                          |
| ---------------------- | ----------------------------------------------------------------------------- |
| `human_edit`           | Text changed on save; includes unified `diff` + `finding_snapshot`            |
| `ai_suggestion`        | Analysis run (initial analyse, save without text change, or save-and-recheck) |
| `submitted_for_review` | Save & Recheck passed all gates → status set to `ready_for_approval`          |

`finding_snapshot` JSON includes `version_number`, `template_check`, `glossary_check`, and `conflict_check` (when run).

**Actor identity:** `actor` in request body or `X-Actor` header (default `anonymous officer`). In the browser: `localStorage.setItem('gr_actor', 'Officer Name')`.

### Versioning rules

- A new `gr_versions` row is created **only when text actually changes** (normalized line endings).
- Repeated **Save Draft** or **Save & Recheck** without edits does **not** bump the version number.
- Each explicit save with changes creates exactly one new version and one audit row (never per keystroke).

### Frontend workflow (review phase)

1. Upload / paste → draft persisted via `POST /drafts` → initial `POST /reasoning/analyze` (logged when draft ID is available).
2. **Review** — edit draft in textarea; toggle **Preview** for highlighted read-only view.
3. **Save Draft** — deterministic template + terminology checks only; status stays `draft`.
4. **Save & Recheck** — above + LLM conflict detection; may promote to `ready_for_approval`.

### Verify in Postgres

```sql
SELECT action_type, finding_snapshot->>'version_number' AS ver,
       finding_snapshot ? 'conflict_check' AS has_conflict,
       left(diff, 80) AS diff_preview, created_at
FROM audit_log
WHERE gr_document_id = <draft_id>
ORDER BY id;

SELECT version_number, left(full_text, 60), created_at
FROM gr_versions
WHERE gr_document_id = <draft_id>
ORDER BY version_number;
```

### New env vars (see `.env.example`)

```bash
GLOSSARY_USE_LLM=false          # deterministic glossary (default)
EMBEDDING_LOCAL_FILES_ONLY=true # offline conflict detection after first embed cache
CONFLICT_TOP_K=5                # faster conflict checks
CONFLICT_MAX_CONTEXT_CHARS=3500
```

### New backend modules

```
backend/
├── services/
│   ├── audit.py    # log_action()
│   └── draft.py    # save_draft_version, save_and_recheck_draft, record_ai_analysis
└── api/routes/
    └── drafts.py   # /drafts endpoints
```

Schema DDL lives in `database/schema.sql` and is applied idempotently via `database/db.py` on API startup (no Alembic — restart uvicorn after pulling schema changes).
