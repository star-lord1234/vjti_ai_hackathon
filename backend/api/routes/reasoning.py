"""
AI Reasoning endpoints router (Q&A, pairwise GR comparison, conflict detection).
"""

from __future__ import annotations

import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reasoning.analyze_models import ConflictCheckSection, DraftAnalysisResponse
from reasoning.glossary import run_glossary_check
from reasoning.glossary.models import GlossaryCheckSection
from reasoning.template import run_template_check
from reasoning.template.models import TemplateCheckSection
from reasoning.llm_reasoner import answer_query, check_conflict, compare_grs
from reasoning.models import ComparisonResult, ConflictFinding, QueryAnswer
from services.draft import record_ai_analysis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reasoning", tags=["reasoning"])


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language question or policy query")
    top_k: int = Field(20, ge=1, le=100, description="Vector top_k seeds")
    hops: int = Field(1, ge=0, le=5, description="Graph citation expansion hops")


class CompareRequest(BaseModel):
    gr_id_a: int = Field(..., description="First GR document ID")
    gr_id_b: int = Field(..., description="Second GR document ID")


class ConflictRequest(BaseModel):
    draft_text: str = Field(..., min_length=1, description="Proposed draft GR text or policy excerpt")
    top_k: int = Field(5, ge=1, le=100, description="Vector top_k seeds")
    hops: int = Field(0, ge=0, le=5, description="Graph citation expansion hops")
    gr_document_id: Optional[int] = Field(
        default=None,
        description="Editable draft ID — when set, initial analysis is written to audit_log",
    )
    actor: Optional[str] = Field(default=None, max_length=128)


@router.post("/query", response_model=QueryAnswer)
def reasoning_query(body: QueryRequest) -> QueryAnswer:
    """
    RAG-driven natural language Q&A grounded strictly in retrieved GR context.
    Note: Can take 3-10 seconds depending on LLM response time.
    """
    try:
        return answer_query(
            query=body.query.strip(),
            top_k=body.top_k,
            hops=body.hops,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI reasoning query engine failed: {e}",
        )


@router.post("/compare", response_model=ComparisonResult)
def reasoning_compare(body: CompareRequest) -> ComparisonResult:
    """
    Pairwise clause-by-clause comparison and contradiction detection between two GRs.
    Note: Can take 3-10 seconds depending on LLM response time.
    """
    try:
        return compare_grs(
            gr_id_a=body.gr_id_a,
            gr_id_b=body.gr_id_b,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI pairwise comparison engine failed: {e}",
        )


@router.post("/conflict", response_model=ConflictFinding)
def reasoning_conflict(body: ConflictRequest) -> ConflictFinding:
    """
    Check proposed draft GR against corpus for conflicts, duplications, or superseding policies.
    Note: Can take 3-10 seconds depending on LLM response time.
    """
    try:
        return check_conflict(
            draft_input=body.draft_text.strip(),
            top_k=body.top_k,
            hops=body.hops,
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI conflict detection engine failed: {e}",
        )


@router.post("/glossary", response_model=GlossaryCheckSection)
def reasoning_glossary(body: ConflictRequest) -> GlossaryCheckSection:
    """
    Bilingual terminology consistency check against the seeded GR glossary.
    Returns status=unavailable (not HTTP 5xx) when the local LLM client is on cooldown.
    """
    return run_glossary_check(body.draft_text.strip())


@router.post("/template", response_model=TemplateCheckSection)
def reasoning_template(body: ConflictRequest) -> TemplateCheckSection:
    """Rule-based GR template / structure compliance check (no LLM)."""
    return run_template_check(body.draft_text.strip())


@router.post("/analyze", response_model=DraftAnalysisResponse)
def reasoning_analyze(
    body: ConflictRequest,
    x_actor: Optional[str] = Header(default=None, alias="X-Actor"),
) -> DraftAnalysisResponse:
    """
    Run conflict, glossary, and template checks in parallel where possible.
    Always returns HTTP 200 with per-section status — partial success is supported.
    """
    from database.db import Database

    draft = body.draft_text.strip()

    def _run_glossary() -> GlossaryCheckSection:
        return run_glossary_check(draft)

    def _run_template() -> TemplateCheckSection:
        return run_template_check(draft)

    conflict_section: ConflictCheckSection
    glossary_section: GlossaryCheckSection
    template_section: TemplateCheckSection

    # Conflict check uses Postgres on the main thread — psycopg connections are not
    # thread-safe, and parallel Database() init used to deadlock on schema migrations.
    db = Database()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            glossary_future = pool.submit(_run_glossary)
            template_future = pool.submit(_run_template)

            try:
                conflict_result = check_conflict(
                    draft_input=draft,
                    top_k=body.top_k,
                    hops=body.hops,
                    db=db,
                )
                conflict_section = ConflictCheckSection(status="ok", result=conflict_result)
            except Exception as exc:
                logger.exception("Conflict check failed during /analyze: %s", exc)
                conflict_section = ConflictCheckSection(status="error", reason=str(exc))

            glossary_section = glossary_future.result()
            template_section = template_future.result()

        if body.gr_document_id is not None:
            draft_row = db.get_draft_document(body.gr_document_id)
            if draft_row:
                actor = (body.actor or x_actor or "anonymous").strip() or "anonymous"
                record_ai_analysis(
                    db,
                    body.gr_document_id,
                    actor,
                    version_number=int(draft_row.get("version_number") or 1),
                    template_check=template_section,
                    glossary_check=glossary_section,
                    conflict_result=conflict_section.result
                    if conflict_section.status == "ok"
                    else None,
                    conflict_error=conflict_section.reason
                    if conflict_section.status == "error"
                    else None,
                )
            else:
                logger.warning(
                    "Analyze audit skipped — draft %s not found",
                    body.gr_document_id,
                )

        return DraftAnalysisResponse(
            conflict_check=conflict_section,
            glossary_check=glossary_section,
            template_check=template_section,
        )
    finally:
        db.close()


import json

from fastapi.responses import StreamingResponse


@router.post("/analyze-stream")
def reasoning_analyze_stream(
    body: ConflictRequest,
    x_actor: Optional[str] = Header(default=None, alias="X-Actor"),
) -> StreamingResponse:
    """
    Stream real-time analysis progress events via Server-Sent Events (SSE).
    Emits granular progress metrics (GR corpus count, candidate count, conflict count).
    """
    from database.db import Database
    from reasoning.clause_parser import extract_draft_clauses

    draft = body.draft_text.strip()
    actor = (body.actor or x_actor or "anonymous").strip() or "anonymous"

    def event_stream():
        # Step 1: Initial event
        yield f"event: progress\ndata: {json.dumps({'step': 'read', 'label': 'Reading Document', 'detail': f'Parsing {len(draft)} chars of draft text', 'count': len(draft)}, ensure_ascii=False)}\n\n"

        # Step 2: Clause extraction
        clauses = extract_draft_clauses(draft)
        yield f"event: progress\ndata: {json.dumps({'step': 'extract', 'label': 'Extracting Clauses', 'detail': f'Identified {len(clauses)} operative resolution clauses', 'count': len(clauses)}, ensure_ascii=False)}\n\n"

        # Step 3: Database & Retrieval
        db = Database()
        try:
            total_grs = db.count()
            yield f"event: progress\ndata: {json.dumps({'step': 'corpus', 'label': 'Corpus Search', 'detail': f'Searching across {total_grs:,} statutory Government Resolutions', 'count': total_grs}, ensure_ascii=False)}\n\n"

            def _run_glossary() -> GlossaryCheckSection:
                return run_glossary_check(draft)

            def _run_template() -> TemplateCheckSection:
                return run_template_check(draft)

            conflict_section: ConflictCheckSection
            glossary_section: GlossaryCheckSection
            template_section: TemplateCheckSection

            with ThreadPoolExecutor(max_workers=2) as pool:
                glossary_future = pool.submit(_run_glossary)
                template_future = pool.submit(_run_template)

                yield f"event: progress\ndata: {json.dumps({'step': 'detect', 'label': 'Detecting Conflicts', 'detail': 'Running vector search & Neo4j citation graph expansion…'}, ensure_ascii=False)}\n\n"

                try:
                    conflict_result = check_conflict(
                        draft_input=draft,
                        top_k=body.top_k,
                        hops=body.hops,
                        db=db,
                    )
                    conflict_section = ConflictCheckSection(status="ok", result=conflict_result)
                    conflicts_count = len(conflict_result.conflict_pairs or []) if conflict_result else 0
                    yield f"event: progress\ndata: {json.dumps({'step': 'analyse', 'label': 'Generating Analysis', 'detail': f'Analysis complete — {conflicts_count} conflict(s) evaluated', 'count': conflicts_count}, ensure_ascii=False)}\n\n"
                except Exception as exc:
                    logger.exception("Conflict check failed during /analyze-stream: %s", exc)
                    conflict_section = ConflictCheckSection(status="error", reason=str(exc))
                    yield f"event: progress\ndata: {json.dumps({'step': 'analyse', 'label': 'Generating Analysis', 'detail': f'Conflict evaluation issue: {exc}'}, ensure_ascii=False)}\n\n"

                glossary_section = glossary_future.result()
                template_section = template_future.result()

            if body.gr_document_id is not None:
                draft_row = db.get_draft_document(body.gr_document_id)
                if draft_row:
                    record_ai_analysis(
                        db,
                        body.gr_document_id,
                        actor,
                        version_number=int(draft_row.get("version_number") or 1),
                        template_check=template_section,
                        glossary_check=glossary_section,
                        conflict_result=conflict_section.result
                        if conflict_section.status == "ok"
                        else None,
                        conflict_error=conflict_section.reason
                        if conflict_section.status == "error"
                        else None,
                    )

            final_response = DraftAnalysisResponse(
                conflict_check=conflict_section,
                glossary_check=glossary_section,
                template_check=template_section,
            )

            yield f"event: complete\ndata: {final_response.model_dump_json()}\n\n"
        finally:
            db.close()

    return StreamingResponse(event_stream(), media_type="text/event-stream")
