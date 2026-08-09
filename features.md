# Maharashtra GR Intelligence & Decision Assistance Platform — Features Guide

> **निर्णय सहाय्यता** — An end-to-end AI-powered legal compliance, conflict detection, stakeholder forum, and PDF export platform for Maharashtra Government Resolutions (GRs).

---

## 👥 User Roles & Access Control Summary

The platform provides role-tailored workflows and permissions for different government officials:

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

## 🚀 Complete Feature Breakdown (Start to End)

### 1. 📤 Document Ingestion & AI Conflict Audit (`GR Editor`)
- **Multi-Format Ingestion**: Upload Marathi GR drafts in `.pdf` or `.txt` format with automatic server-side text and OCR extraction.
- **AI Conflict Detection Engine**:
  - **Vector & Graph RAG Search**: Queries PostgreSQL (`pgvector` HNSW index) and Neo4j graph database to detect legal conflicts against historical GRs.
  - **Supersession & Amendment Detection**: Identifies whether the new draft overrides or contradicts existing active policy resolutions.
  - **Cross-Departmental Impact Analysis**: Flags policy conflicts that cross department boundaries (e.g. Finance, Education, General Administration).
  - **Severity Scoring**: Categorizes findings into **High**, **Medium**, and **Low** risk levels based on confidence and policy overlap.
- **Terminology & Glossary Verification**: Checks Devanagari legal terms against standard government Marathi vocabulary.
- **Template Structural Scoring**: Measures draft compliance against official Maharashtra GR layout rules (Subject line, Reference section, Order clause, Signatory rules).

---

### 2. ✏️ Interactive Dual-Pane Editor & Clause Inspector
- **Side-by-Side View**: Dual-pane workspace with document text on the left and structured findings panel on the right.
- **Live Clause Highlighting**: Click any conflict finding to jump directly to the target clause in the document text with amber/red visual highlights.
- **Drafting & Re-Auditing**: Edit draft text in real-time, click **Save Draft** or **Save & Recheck** to get updated clause diffs (`added`, `modified`, `unchanged`).
- **Version Control System**: Full version history tracking for every draft update with modal inspection.

---

### 3. 📖 Original Cited GR Reader (`Corpus Document Viewer`)
- **Direct Citation Inspection**: In the Conflict Details sidebar under *Existing GR provides*, view relevant snippets of cited historical GRs.
- **Full Text Reader Button**: Click **`Read Full Original GR ↗`** inside any conflict card to open a full-height reader modal (`OriginalGRViewerModal`).
- **Complete Devanagari Text**: Renders the complete, original `ocr_text` of cited historical resolutions from the government database with search filtering and copy tools.

---

### 4. 🏛️ Department Forum & Stakeholder Q&A Dashboard (`In-Progress GRs`)
- **Send to Forum**: Drafting officers click **"Send to Forum"** to publish a draft for department-wide review.
- **In-Progress GR Feed Grid**: Visual dashboard listing all shared drafts with version badges, open question counts, and approval status tags.
- **Discussion & Q&A Thread**:
  - Post **Questions**, **Review Notes**, or **Policy Suggestions**.
  - Reply to specific questions and toggle items **Resolved / Open**.
  - Dedicated role badges on all comments.

---

### 5. ✍️ Approval Workflow & Gated PDF Export
- **Official Approval Notes**: Approvers (Joint Secretaries / Department Heads) post an **✅ Approval Note** on the shared draft.
- **Approval Gate**:
  - **Before Approval**: Finalizing exports plain `.txt` files. Forum cards show *⏳ Awaiting Approvals*.
  - **After Approval**: Forum status flips to **`✅ Approved — PDF Ready`**, unlocking the **Download PDF 📄** button.
- **Server-Side PDF Generation (WeasyPrint)**:
  - Generates official PDF documents styled with government letterhead, Seal of Maharashtra, Devanagari typography (`Noto Sans`), margin controls, and verification approval badges.
- **Non-Destructive Export**: Downloading the PDF preserves the document in the forum so other users can continue inspecting or downloading.

---

### 6. 🚫 Forum Banishment / Archival
- **Banish from Dashboard**: Approvers and Admins can click **"Banish from Dashboard 🚫"** on fully approved/finalized GRs (from the feed or detail view) to archive and remove them from the active in-progress forum feed.

---

### 7. 🛡️ System Administration & PDF Template Editor (`Admin Role`)
- **PDF Template Editor Tab**: Exclusive tab for system administrators.
- **Customizable Letterhead Fields**:
  - Government Department Name (e.g. *महाराष्ट्र शासन*).
  - Sub-header Line (e.g. *उच्च व तंत्र शिक्षण विभाग*).
  - Order / Footer Text (e.g. *महाराष्ट्राचे राज्यपाल यांच्या आदेशानुसार व नावाने*).
  - Font Selection & Page Margin Controls (points).
  - Base64 Seal / Emblem Logo Upload.
- **Live PDF Preview**: Render live PDF previews directly in the browser via `GET /template/preview`.

---

## ⚡ 3-Tier Caching & Optimization Architecture

The platform incorporates a **3-Tier Caching System** designed for high throughput, minimal database load, and instant interactive auditing:

```
+-----------------------------------------------------------------------------------+
|                        TIER 1: RECENT GR DOCUMENT CACHE                           |
|       In-Memory Document Session Cache (Avoids redundant PDF/OCR extraction)       |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|               TIER 2: INCREMENTAL CLAUSE & CHUNK-LEVEL DIFF CACHE                 |
|       `diff_clauses()` computes Added/Modified/Unchanged Clause Chunks           |
|       -> Unchanged chunks reuse cached findings; ONLY modified chunks re-audited   |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|               TIER 3: DATABASE & KNOWLEDGE GRAPH QUERY CACHING                    |
|   PostgreSQL pgvector HNSW Vector Cache + In-Memory Neo4j Citation Graph Map      |
+-----------------------------------------------------------------------------------+
```

### 1. 📁 Tier 1: Recent GR Document Session Cache
- **Document Session Persistence**: When a GR document has been recently loaded or submitted for conflict detection, the parsed text structure, metadata, and generated vector embeddings are cached in server memory.
- **Instant Re-Inspection**: Submitting or re-opening a recently processed GR bypasses redundant OCR text extraction and heavy document parsing.

---

### 2. 🧩 Tier 2: Incremental Clause & Chunk-Level Diff Cache (Minor Edit Recheck)
- **Granular Clause Diffing (`diff_clauses()`)**: When minor changes or clause edits are made in the editor during **Save & Recheck**, the system computes an incremental clause-level diff (`added`, `modified`, `unchanged`).
- **Selective Chunk Re-Auditing**: Unchanged clauses reuse previously computed conflict findings, audit scores, and glossary checks. **Only newly added or modified clause chunks** are re-audited against the vector database and graph engine, reducing API latency and LLM token overhead by up to 80%.

---

### 3. 🗄️ Tier 3: Database & Knowledge Graph Query Caching
- **HNSW Vector Index RAM Caching**: PostgreSQL `pgvector` utilizes **HNSW (Hierarchical Navigable Small World)** vector index caching (`hnsw.ef_search = 64`) to keep high-dimensional embedding vectors in RAM for sub-millisecond similarity lookups.
- **In-Memory Canonical ID & Graph Edge Map**: `get_canonical_id_map()` caches canonical GR numbers mapped to database document IDs, while Neo4j graph relationships (`CITES`, `SUPERSEDES`) are cached in memory to eliminate redundant database traversals.
- **Asynchronous Thread Pool Offloading**: Heavy database queries, vector computations, and WeasyPrint PDF compilations are offloaded to worker thread pools (`run_in_threadpool` / `anyio.to_thread`), keeping the main FastAPI event loop non-blocking.
- **Frontend Web Worker & Client State Caching**: Offloads PDF parsing (`pdf.worker.mjs`) to browser Web Workers, while React state optimistically caches feed items, version counts, and approval badges.

---

## 🏛️ Overall System Architecture Features

```
+-----------------------------------------------------------------------------------+
|                                  PRESENTATION LAYER                               |
|               React 18 + TypeScript + Vite + TailwindCSS + Web Workers            |
+-----------------------------------------------------------------------------------+
                                          |  HTTP / REST
                                          v
+-----------------------------------------------------------------------------------+
|                                    API GATEWAY                                    |
|              FastAPI REST Backend (Python 3.14 + CORS + Global Handler)           |
+-----------------------------------------------------------------------------------+
                                   /      |      \
                                  /       |       \
                                 v        v        v
+----------------------------------+ +----------+ +---------------------------------+
|          PERSISTENCE LAYER       | | GRAPH DB | |           PDF ENGINE            |
| PostgreSQL 16 + pgvector (HNSW)  | |  Neo4j   | |  WeasyPrint + Pango/GObject     |
| (GR Documents, Versions, Forum)  | | CITES DB | | (Devanagari Letterhead Export) |
+----------------------------------+ +----------+ +---------------------------------+
```

1. **Hybrid Vector + Knowledge Graph RAG Architecture**:
   - Dual-retrieval pipeline combining dense semantic vector search with structural graph traversal (`CITES`, `SUPERSEDES`, `DEPT_BELONGS_TO`), achieving ultra-high precision on legal citation resolution.

2. **Decoupled 3-Tier Architecture**:
   - Strict separation between **Presentation Layer** (React SPA), **Service Layer** (FastAPI API), and **Persistence Layer** (PostgreSQL + Neo4j + Server Filesystem).

3. **CORS & Resilience Infrastructure**:
   - Centralized global exception handler (`@app.exception_handler(Exception)`) automatically attaches CORS headers (`Access-Control-Allow-Origin`, `Access-Control-Expose-Headers`) even on server errors, ensuring browser request transparency.

4. **Headless PDF Rendering Pipeline**:
   - Modular `pdf_export.py` service dynamically injects base64 emblems, CSS templates, font fallbacks (`Noto Sans Devanagari`, `Lohit Devanagari`), and approval signatures into clean A4 PDF documents.
