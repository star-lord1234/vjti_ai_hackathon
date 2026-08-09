# Maharashtra GR Intelligence & Decision Assistance Platform — निर्णय सहाय्यता

> **निर्णय सहाय्यता** — An end-to-end AI-powered legal compliance, conflict detection, stakeholder forum, and PDF export platform for Maharashtra Government Resolutions (GRs).

---

## 📌 Executive Overview

The **Maharashtra GR Intelligence & Decision Assistance Platform** provides comprehensive AI-driven intelligence over the Maharashtra Government Resolution (GR) legal corpus. It connects database ingestion, hybrid RAG retrieval (combining dense vector embeddings with structural knowledge graphs), real-time legal conflict auditing, an interactive dual-pane drafting workspace, an institutional cited document reader, a stakeholder Q&A department forum, and a gated, server-side PDF export pipeline with customizable government letterhead templates.

Designed for **air-gapped and local-first deployment**, the system operates fully offline using local PostgreSQL with `pgvector`, Neo4j graph database, and WeasyPrint rendering engines.

---

## 👥 User Roles & Access Control Matrix

The platform provides role-tailored workflows and granular permissions for different government officials:

| Feature / Capability | 🖊️ Drafting Officer (`drafter`) | 🔍 Employee / Reviewer (`reviewer`) | 👔 Joint Secretary / Approver (`approver`) | 🛡️ System Admin (`admin`) |
|---|:---:|:---:|:---:|:---:|
| **Upload GR Draft (PDF/TXT)** | ✅ | ❌ | ❌ | ❌ |
| **Edit Draft & Run Conflict Auditor** | ✅ | ❌ | ❌ | ❌ |
| **Save & Recheck Clause Diff** | ✅ | ❌ | ❌ | ❌ |
| **Version History & Inspection** | ✅ | ✅ | ✅ | ✅ |
| **Send Draft to Department Forum** | ✅ | ❌ | ❌ | ❌ |
| **Inspect Shared Forum GRs** | ✅ | ✅ | ✅ | ✅ |
| **Post Q&A, Comments & Suggestions** | ✅ | ✅ | ✅ | ✅ |
| **Post Official Approval Note** | ❌ | ❌ | ✅ | ❌ |
| **Read Full Original Cited GRs** | ✅ | ✅ | ✅ | ✅ |
| **Download Export (.txt)** | ✅ | ✅ | ✅ | ✅ |
| **Export Formatted PDF (Letterhead)** | ❌ (Plain txt) | ❌ (Plain txt) | ✅ (Once Approved) | ✅ |
| **Banish/Archive GR from Forum** | ❌ | ❌ | ✅ | ✅ |
| **Edit PDF Letterhead Template** | ❌ | ❌ | ❌ | ✅ |

---

## 🚀 Key Platform Features & Modules

```
                        DRAFT LIFECYCLE & AUDIT PIPELINE
                        
    ┌────────────────────────┐         ┌────────────────────────┐
    │  Upload Draft (PDF/TXT)│ ──────▶ │ AI Conflict Auditor    │
    └────────────────────────┘         │ (pgvector + Neo4j RAG) │
                │                      └───────────┬────────────┘
                ▼                                  │
    ┌────────────────────────┐                     │
    │ Dual-Pane Editor &     │ ◄───────────────────┘
    │ Incremental Clause Diff│
    └───────────┬────────────┘
                │
                ▼
    ┌────────────────────────┐         ┌────────────────────────┐
    │ Department Forum Feed  │ ──────▶ │ Stakeholder Q&A &      │
    │ (In-Progress GRs)      │         │ Official Approval Notes│
    └────────────────────────┘         └───────────┬────────────┘
                                                   │
                                                   ▼
    ┌────────────────────────┐         ┌────────────────────────┐
    │ Banish from Forum 🚫   │ ◄────── │ Gated PDF Export 📄     │
    │ (Archival)             │         │ (WeasyPrint Letterhead)│
    └────────────────────────┘         └────────────────────────┘
```

### 1. 📤 Multi-Format Ingestion & AI Conflict Audit
- **Multi-Format Ingestion**: Upload Marathi GR drafts in `.pdf` or `.txt` format with automatic server-side text extraction and OCR processing.
- **Hybrid Vector + Knowledge Graph RAG**:
  - Dense semantic search using PostgreSQL `pgvector` (768-dim multilingual embeddings).
  - Neo4j graph expansion (`:GR-[:CITES]->:GR`, `:GR-[:SUPERSEDES]->:GR`) for deep legal context retrieval.
- **Supersession & Amendment Detection**: Flags draft clauses that override, contradict, or duplicate existing active resolutions.
- **Cross-Departmental Impact Analysis**: Identifies inter-departmental conflicts (e.g. Finance, Higher & Technical Education, General Administration).
- **Bilingual Terminology Checker**: Scans Devanagari legal terms against standard government Marathi vocabulary (`glossary.json`).
- **Template Structural Scoring**: Evaluates compliance against official layout rules (Subject, Reference section, Operative clause, Signatories).

---

### 2. ✏️ Dual-Pane Editor & Incremental Clause Diffing
- **Side-by-Side Workspace**: Document text editor on the left and structured audit findings on the right.
- **Interactive Clause Highlighting**: Click any conflict finding to jump directly to the target clause in the document text with line/clause highlights.
- **Incremental Re-Auditing**: Edit draft text in real time, click **Save Draft** or **Save & Recheck** to execute incremental diffing (`added`, `modified`, `unchanged` clauses).
- **Version Control System**: Full version history tracking (`gr_versions`) with diff inspection across iteration snapshots.

---

### 3. 📖 Original Cited GR Reader (`Corpus Document Viewer`)
- **Direct Citation Inspection**: View conflicting snippets from historical GRs in the sidebar under *Existing GR provides*.
- **Full Text Reader Button**: Click **`Read Full Original GR ↗`** inside any conflict card to open a dedicated reader modal (`OriginalGRViewerModal`).
- **Complete Devanagari Text**: Renders the complete, original `ocr_text` of cited historical resolutions from the database with in-text search filtering and copy tools.

---

### 4. 🏛️ Department Forum & Stakeholder Q&A Dashboard
- **Send to Forum**: Drafting officers click **"Send to Forum"** to publish a draft for department-wide review.
- **In-Progress GR Feed Grid**: Visual dashboard listing all shared drafts with version badges, open question counts, and approval status tags.
- **Discussion & Q&A Thread**: Post **Questions**, **Review Notes**, or **Policy Suggestions**; reply to specific items and mark questions resolved/open.

---

### 5. ✍️ Approval Workflow & Gated PDF Export
- **Official Approval Notes**: Approvers (Joint Secretaries / Department Heads) post an **✅ Approval Note** on the shared draft.
- **Approval Gate**:
  - **Before Approval**: Finalizing exports plain `.txt` files. Forum cards display *⏳ Awaiting Approvals*.
  - **After Approval**: Status flips to **`✅ Approved — PDF Ready`**, unlocking **Download PDF 📄**.
- **Server-Side PDF Generation (WeasyPrint)**: Generates official PDF documents styled with government letterhead, Seal of Maharashtra, Devanagari typography (`Noto Sans`), margin controls, and verification approval badges.
- **Non-Destructive Export**: Downloading the PDF preserves the document in the forum so other users can continue inspecting or downloading.

---

### 6. 🚫 Forum Banishment / Archival
- **Banish from Dashboard**: Approvers and Admins can click **"Banish from Dashboard 🚫"** on fully approved/finalized GRs (from the feed or detail view) to archive and remove them from the active in-progress forum feed.

---

### 7. 🛡️ System Administration & PDF Template Editor
- **PDF Template Editor Tab**: Exclusive tab for system administrators.
- **Customizable Letterhead Fields**: Government Department Name, Sub-header Line, Order/Footer Text, Font Selection, Page Margins (pt), and Emblem/Logo Upload (Base64).
- **Live Browser PDF Preview**: Render live PDF previews directly in the browser via `GET /template/preview`.

---

## ⚡ 3-Tier Caching & Optimization Architecture

The platform incorporates a **3-Tier Caching System** designed for high throughput, minimal database load, and instant interactive auditing:

```
+-----------------------------------------------------------------------------------+
|                        TIER 1: RECENT GR DOCUMENT CACHE                           |
|       In-Memory Document Session Cache (Avoids redundant PDF/OCR extraction)       |
+-----------------------------------------------------------------------------------+
                                          │
                                          ▼
+-----------------------------------------------------------------------------------+
|               TIER 2: INCREMENTAL CLAUSE & CHUNK-LEVEL DIFF CACHE                 |
|       `diff_clauses()` computes Added/Modified/Unchanged Clause Chunks           |
|       -> Unchanged chunks reuse cached findings; ONLY modified chunks re-audited   |
+-----------------------------------------------------------------------------------+
                                          │
                                          ▼
+-----------------------------------------------------------------------------------+
|               TIER 3: DATABASE & KNOWLEDGE GRAPH QUERY CACHING                    |
|   PostgreSQL pgvector HNSW Vector Cache + In-Memory Neo4j Citation Graph Map      |
+-----------------------------------------------------------------------------------+
```

1. **Tier 1 — Recent GR Document Session Cache**: Caches parsed text structure, metadata, and generated vector embeddings when a GR document is loaded or analyzed, bypassing redundant OCR text extraction and heavy document parsing upon re-inspection.
2. **Tier 2 — Incremental Clause & Chunk-Level Diff Cache (`diff_clauses()`)**: When minor changes or clause edits are made in the editor during **Save & Recheck**, the system computes an incremental clause-level diff (`added`, `modified`, `unchanged`). Unchanged clauses reuse previously cached conflict findings and glossary checks. **Only newly added or modified clause chunks** are re-audited against the vector database and graph engine, cutting latency and token overhead by up to 80%.
3. **Tier 3 — Database & Knowledge Graph Query Caching**:
   - **HNSW Vector RAM Caching**: PostgreSQL `pgvector` keeps embedding vectors in RAM (`hnsw.ef_search = 64`) for sub-millisecond similarity searches.
   - **In-Memory Canonical ID & Graph Edge Map**: `get_canonical_id_map()` caches canonical GR numbers mapped to DB IDs, while Neo4j graph relationships (`CITES`, `SUPERSEDES`) are cached in memory to eliminate redundant database traversals.
   - **Async Thread Pool Offloading**: Heavy database queries, vector computations, and WeasyPrint PDF compilations are offloaded to worker thread pools (`run_in_threadpool` / `anyio.to_thread`), keeping the main FastAPI event loop non-blocking.
   - **Frontend Web Worker & Client State Caching**: Offloads PDF parsing (`pdf.worker.mjs`) to browser Web Workers, while React state optimistically caches feed items, version counts, and approval badges.

---

## 🏛️ Overall System Architecture

```
+-----------------------------------------------------------------------------------+
|                                  PRESENTATION LAYER                               |
|               React 18 + TypeScript + Vite + TailwindCSS + Web Workers            |
+-----------------------------------------------------------------------------------+
                                          │  HTTP / REST
                                          ▼
+-----------------------------------------------------------------------------------+
|                                    API GATEWAY                                    |
|              FastAPI REST Backend (Python 3.14 + CORS + Global Handler)           |
+-----------------------------------------------------------------------------------+
                                   /      │      \
                                  /       │       \
                                 ▼        ▼        ▼
+----------------------------------+ +----------+ +---------------------------------+
|          PERSISTENCE LAYER       | | GRAPH DB | |           PDF ENGINE            |
| PostgreSQL 16 + pgvector (HNSW)  | |  Neo4j   | |  WeasyPrint + Pango/GObject     |
| (GR Documents, Versions, Forum)  | | CITES DB | | (Devanagari Letterhead Export) |
+----------------------------------+ +----------+ +---------------------------------+
```

---

## 🛠️ Technology Stack

| Layer | Technology / Tool |
|---|---|
| **Backend Framework** | Python 3.14 / 3.10+, FastAPI, Uvicorn, Pydantic v2 |
| **Relational & Vector DB** | PostgreSQL 16+ with `pgvector` extension (768-dim embeddings, HNSW index) |
| **Knowledge Graph DB** | Neo4j 5+ (Bolt protocol, `CITES` and `SUPERSEDES` graph relationships) |
| **Embeddings** | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` |
| **PDF Generation** | WeasyPrint + Pango / GObject + Devanagari Font Stack (`Noto Sans`) |
| **Frontend Framework** | React 18, TypeScript, Vite 6, Tailwind CSS 4, Lucide icons |
| **PDF Worker** | `pdfjs-dist` (client-side text extraction & Web Worker offloading) |
| **Testing & Tooling** | `pytest`, `httpx`, Make targets |

---

## 📁 Repository Structure

```
vjti/
├── backend/
│   ├── api/
│   │   ├── main.py              # FastAPI application & global exception handler
│   │   └── routes/              # search, documents, graph, reasoning, drafts, forum, template, chat
│   ├── data/
│   │   ├── glossary.json        # Bilingual terminology seed list
│   │   └── gr_template_structure.json
│   ├── database/
│   │   ├── db.py                # Database client, psycopg 3 queries, schema migrations
│   │   └── schema.sql
│   ├── embeddings/
│   │   ├── embed.py             # Multilingual MPNet vector embedder
│   │   └── search.py            # pgvector HNSW cosine similarity search
│   ├── graph/
│   │   ├── reference_resolver.py
│   │   ├── neo4j_loader.py
│   │   └── neo4j_query.py
│   ├── parser/
│   │   ├── rule_extractor.py    # Header regex parser
│   │   └── section_locator.py   # Position-aware section locator
│   ├── reasoning/
│   │   ├── llm_reasoner.py      # Conflict, query, and comparison engines
│   │   ├── glossary/            # Terminology verification
│   │   └── template/            # Rule-based layout auditor
│   ├── services/
│   │   ├── audit.py             # Centralized audit log service
│   │   ├── draft.py             # Draft persistence & incremental diffing
│   │   └── pdf_export.py        # WeasyPrint PDF generation engine
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── App.tsx          # Main UI SPA & phase router
│   │   │   └── components/      # DepartmentForumView, SharedGRDetailView,
│   │   │                        # OriginalGRViewerModal, PdfTemplateEditor,
│   │   │                        # HeaderBar, RoleContext, CommentThread
│   │   └── lib/                 # api.ts, adapters.ts, pdf.ts
├── features.md                  # Comprehensive features & architecture guide
├── Makefile
├── .env.example
└── README.md
```

---

## 🔌 Complete API Endpoint Reference

| Method | Endpoint Path | Description |
|---|---|---|
| `GET` | `/health` | Postgres, Neo4j, embedding coverage, and store-sync status |
| `GET` | `/search?q=...&top_k=20&hops=1` | Hybrid vector + graph search over legal corpus |
| `GET` | `/documents` | Paginated GR document list |
| `GET` | `/documents/{gr_id}` | Full GR document details including `ocr_text` |
| `GET` | `/documents/lookup?query=...` | Resolves GR by ID, canonical number, or filename |
| `GET` | `/documents/{gr_id}/citations` | Raw JSONB citations & resolved Neo4j target GRs |
| `GET` | `/graph/{gr_id}?hops=2` | Citation subgraph visualization data |
| `POST` | `/reasoning/analyze` | Parallel conflict + glossary + template audit |
| `POST` | `/drafts` | Create a new editable GR draft |
| `GET` | `/drafts/{draft_id}` | Fetch draft summary and full text |
| `POST` | `/drafts/{draft_id}/save` | Save draft version with deterministic checks |
| `POST` | `/drafts/{draft_id}/save-and-recheck` | Save draft & run incremental conflict recheck |
| `GET` | `/drafts/{draft_id}/pdf` | Export GR draft as a formatted PDF |
| `POST` | `/drafts/{draft_id}/banish` | Banish/archive finalized GR from Department Forum |
| `GET` | `/forum/in-progress` | Fetch all shared in-progress GRs for Department Forum |
| `GET` | `/forum/{gr_id}` | Shared GR detail including Q&A comments & approval notes |
| `POST` | `/forum/{gr_id}/comments` | Post question, review comment, or approval note |
| `GET` | `/template` | Fetch PDF letterhead template configuration |
| `PUT` | `/template` | Update PDF letterhead template configuration |
| `GET` | `/template/preview` | Render live PDF template preview |
| `POST` | `/chat/message` | Document-aware assistant chat |

---

## ⚡ Quick Start Guide

### 1. Clone & Setup Environment

```bash
git clone <your-repo-url>
cd vjti

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend dependencies
pip install -r backend/requirements.txt
```

### 2. Environment Configuration

Copy `.env.example` to `backend/.env`:

```bash
cp .env.example backend/.env
```

Ensure `backend/.env` contains your database and server settings:

```env
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

# Frontend Origin CORS
FRONTEND_ORIGIN=http://localhost:5173
```

### 3. PostgreSQL & Neo4j Setup

```bash
# Create database
createdb maha_gr

# Schema and migrations apply automatically on API startup!
```

Ensure your local Neo4j DBMS is running via Neo4j Desktop or local service.

### 4. Start Backend API Server

```bash
cd backend
.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI docs will be available at `http://localhost:8000/docs`.

### 5. Start Frontend UI

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## 🧪 Testing

Run backend unit and integration tests:

```bash
make test-unit
```

---

## 📄 License & Data Usage

Original Government Resolutions remain subject to their respective government publication terms. Code and schemas in this repository are maintained for the **Maharashtra GR Intelligence & Decision Assistance Platform**.
