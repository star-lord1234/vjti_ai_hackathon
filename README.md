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
│   └── neo4j_loader.py
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
