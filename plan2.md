# Plan 2: SRS Requirements Not Covered by the Current Project

This document lists the requirements from the SRS that are either not implemented, only partially implemented, or not yet enforceable in the current project.

## Source used

- SRS file: SRS.pdf
- Project review basis: current repo features, backend logic, frontend workflow, and the planning notes in planning.txt

---

## 1) Requirements not covered by the project

### 1. Official archive verification for cited references

- SRS references: FR-2, FR-3
- Requirement: The system shall verify whether each cited GR, circular, or court order exists in the official archive / mahGRs dataset, and highlight missing or incorrect references.
- Current status: Not fully covered.
- Why it is missing:
  - The project performs citation extraction and graph-based matching using local corpus data, but it does not perform a full, authoritative verification against the official Maharashtra government archive workflow.
  - There is no explicit check that marks a cited reference as valid/invalid against the official archive record set, beyond the local GR corpus and graph heuristics.

### 2. Full legal-source traceability and audit trail

- SRS references: FR-15, NFR-6
- Requirement: The system shall keep an audit trail of all AI suggestions and human edits, and every AI suggestion must show the source document or rule that triggered it.
- Current status: Partially covered / not complete.
- Why it is missing:
  - The app shows excerpts and GR numbers, but there is no persistent audit log of proposal creation, acceptance, rejection, or revision history.
  - There is no explicit version-controlled record of human edits vs. AI suggestions in a proper audit-trail model.
  - Source provenance is present in a lightweight form, but not in a formal legal review workflow.

### 3. Final export in PDF / DOCX format

- SRS reference: FR-16
- Requirement: The system shall allow export of the final draft as PDF / DOCX.
- Current status: Not covered.
- Why it is missing:
  - The current project supports text export and report export, but not actual PDF or DOCX final-draft export.
  - There is no conversion pipeline from processed draft text to official document formats.

### 4. State Data Centre / on-premise security requirement

- SRS reference: NFR-2
- Requirement: Sensitive drafts shall not leave the on-premise / State Data Centre environment.
- Current status: Not covered.
- Why it is missing:
  - The current system uses local Ollama for analysis and chat tasks.
  - This means draft content and sensitive legal text can leave the local environment unless the deployment is specifically isolated and approved for external access.
  - The project does not provide a strict on-premise-only deployment mode for all analysis flows.

### 5. Real operational reliability target for office-hours availability

- SRS reference: NFR-4
- Requirement: System uptime target is at least 95% during office hours.
- Current status: Not covered.
- Why it is missing:
  - There is no production monitoring, failover logic, health SLA dashboard, or uptime tracking in the project.
  - There are no deployment safeguards, auto-restarts, or service-health checks designed to meet a 95% uptime requirement.

### 6. Fine-tuned Indic NLP models and entity recognition

- SRS architecture section: Data layer + NLP Engine
- Requirement: The system architecture mentions fine-tuned Indic models and entity recognition.
- Current status: Not covered.
- Why it is missing:
  - The current project uses general multilingual embeddings and regex/LLM-based extraction rather than a dedicated fine-tuned Marathi legal NLP engine.
  - There is no dedicated named-entity recognition pipeline for legal entities, departments, provisions, dates, subjects, and office designations as a first-class module.

### 7. Full official archive ingestion pipeline from PDF/HTML to text to embeddings

- SRS architecture section: Data Layer + NLP Engine
- Requirement: The system shall ingest official archive documents from PDF/HTML into text, normalize them, and create embeddings.
- Current status: Partially covered.
- Why it is missing:
  - The project ingests the Maharashtra GR corpus from local OCR text files, but the SRS expects ingestion from official archives and a formal archive normalization pipeline.
  - It does not implement a complete production ingestion pipeline from official PDF/HTML sources into the database with tracked provenance and re-ingestion workflow.

### 8. Mandatory rejection workflow for invalid GR format

- SRS references: FR-10, FR-11, FR-12
- Requirement: The system shall enforce the structure defined by the Manual of Office Procedure and reject or warn when any mandatory section is missing or wrongly formatted.
- Current status: Partially covered.
- Why it is missing:
  - The current template checker does flag missing or misordered sections, and the frontend blocks draft export when issues exist.
  - However, this is still a review/warning system rather than a strict issuance gate that enforces the rule at the document-authoring workflow level with formal rejection states and workflow blocking.

### 9. Full structured reference validation for court orders and circulars

- SRS references: FR-1, FR-2, FR-3
- Requirement: Extract all cited GRs, circulars, and court orders from the draft preamble and validate each reference against the archive.
- Current status: Not fully covered.
- Why it is missing:
  - The project handles GR reference extraction and graph-based linkage, but there is no complete validation pipeline for all reference categories including court orders and circulars with authoritative lookups and status tagging.
  - The logic is stronger for GR-to-GR references than for mixed legal reference types.

### 10. Formal document versioning / proposal lifecycle

- SRS references: FR-15, user workflow description
- Requirement: Keep an audit trail of all AI suggestions and human edits.
- Current status: Not covered.
- Why it is missing:
  - There is no draft version history, suggestion approval trail, or tracked lifecycle across draft revisions.
  - The app supports review and export, but not a formal legal-document lifecycle management flow.

### 11. Full deployment compatibility for government production environment

- SRS references: NFR-1 through NFR-6
- Requirement: The system should be usable in a real public-sector production environment with controlled data flow, explainability, reliability, and operational governance.
- Current status: Not covered.
- Why it is missing:
  - There is no governance layer for deployment approvals, role-based access, access logs, or production monitoring needed for a state office environment.
  - The current project is closer to a research/prototype workflow than a ready-for-government-production compliance system.

---

## 2) Requirements that are covered or mostly covered

These are the major SRS requirements that the project already addresses at least in a working prototype form:

- Conflict detection across related GRs and departments
- Semantic search using embeddings and graph expansion
- Glossary-based Marathi–English terminology validation
- GR template structure checking for mandatory sections and ordering
- Web dashboard for draft upload / review
- Draft review and reporting/export workflow in a basic form
- Bilingual support for Marathi and English text handling
- Explainability through retrieved excerpts and source GR labels

---

## 3) Summary of the biggest missing items

If the goal is to align the project with the SRS as written, the most important gaps are:

1. Official archive verification of citations
2. Full audit trail of AI suggestions and human edits
3. PDF/DOCX document export
4. On-premise-only data processing compliance
5. Production reliability and monitoring
6. Fine-tuned Indic legal NLP / entity recognition
7. Full reference-category validation beyond GR-to-GR matching

---

## 4) Planning conclusion

The project is a strong prototype for AI-assisted GR review, conflict detection, glossary checks, and template validation, but it is not yet a complete SRS-compliant government workflow system. The major remaining work is not just model quality; it is also governance, traceability, deployment compliance, and official-document lifecycle management.
