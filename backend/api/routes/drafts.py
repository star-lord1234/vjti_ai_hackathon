"""Editable draft lifecycle endpoints with audit trail."""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException, Query

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Database
from reasoning.analyze_models import ConflictCheckSection
from reasoning.glossary.models import GlossaryCheckSection
from reasoning.template.models import TemplateCheckSection
from services.draft import save_and_recheck_draft, save_draft_version

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/drafts", tags=["drafts"])


class DraftCreateRequest(BaseModel):
    full_text: str = Field(..., min_length=1)
    filename: str = Field(default="draft.txt", max_length=255)
    actor: Optional[str] = Field(default=None, max_length=128)
    subject_mr: Optional[str] = Field(default=None, max_length=500)


class DraftSaveRequest(BaseModel):
    full_text: str = Field(..., min_length=1)
    actor: Optional[str] = Field(default=None, max_length=128)


class DraftSummary(BaseModel):
    id: int
    filename: str
    status: str
    version_number: int
    full_text: str


class DraftSaveResponse(BaseModel):
    draft: DraftSummary
    template_check: TemplateCheckSection
    glossary_check: GlossaryCheckSection


class ClauseDiffResult(BaseModel):
    """Which clauses changed vs stayed the same between two draft versions."""
    added: list[str] = []
    modified: list[str] = []
    unchanged: list[str] = []
    has_changes: bool = False


class DraftRecheckResponse(DraftSaveResponse):
    conflict_check: ConflictCheckSection
    clause_diff: ClauseDiffResult = ClauseDiffResult()


def _resolve_actor(body_actor: Optional[str], x_actor: Optional[str]) -> str:
    if body_actor and body_actor.strip():
        return body_actor.strip()
    if x_actor and x_actor.strip():
        return x_actor.strip()
    return "anonymous"


def _unique_draft_filename(filename: str) -> str:
    base = filename.strip() or "draft.txt"
    return f"draft-{uuid.uuid4().hex[:12]}-{base}"


def _to_draft_summary(row: Dict[str, Any]) -> DraftSummary:
    return DraftSummary(
        id=int(row["id"]),
        filename=row.get("filename") or "draft.txt",
        status=row.get("status") or "draft",
        version_number=int(row.get("version_number") or 1),
        full_text=row.get("full_text") or row.get("ocr_text") or "",
    )


class VersionHistoryItem(BaseModel):
    id: int
    gr_document_id: int
    version_number: int
    full_text: str
    actor: str = "anonymous"
    lines_added: int = 0
    lines_deleted: int = 0
    chars_added: int = 0
    chars_deleted: int = 0
    raw_diff: Optional[str] = None
    created_at: Optional[str] = None


@router.post("", response_model=DraftSummary)
def create_draft(
    body: DraftCreateRequest,
    x_actor: Optional[str] = Header(default=None, alias="X-Actor"),
) -> DraftSummary:
    """Create a persisted editable draft with version 1."""
    actor = _resolve_actor(body.actor, x_actor)
    db = Database()
    try:
        doc_id = db.create_draft_document(
            filename=_unique_draft_filename(body.filename),
            full_text=body.full_text.strip(),
            subject_mr=body.subject_mr,
            actor=actor,
        )
        draft = db.get_draft_document(doc_id)
        if not draft:
            raise HTTPException(status_code=500, detail="Failed to load created draft.")
        logger.info("Created draft %s by %s", doc_id, actor)
        return _to_draft_summary(draft)
    finally:
        db.close()


@router.get("/{draft_id}", response_model=DraftSummary)
def get_draft(draft_id: int) -> DraftSummary:
    db = Database()
    try:
        draft = db.get_draft_document(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
        return _to_draft_summary(draft)
    finally:
        db.close()


@router.post("/{draft_id}/save", response_model=DraftSaveResponse)
def save_draft(
    draft_id: int,
    body: DraftSaveRequest,
    x_actor: Optional[str] = Header(default=None, alias="X-Actor"),
) -> DraftSaveResponse:
    """Explicit save — deterministic checks only, status remains draft."""
    actor = _resolve_actor(body.actor, x_actor)
    db = Database()
    try:
        result = save_draft_version(
            db,
            draft_id,
            body.full_text.strip(),
            actor,
        )
        return DraftSaveResponse(
            draft=_to_draft_summary(result["draft"]),
            template_check=result["template_check"],
            glossary_check=result["glossary_check"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Save draft failed for %s: %s", draft_id, exc)
        raise HTTPException(status_code=502, detail=f"Save draft failed: {exc}") from exc
    finally:
        db.close()


@router.post("/{draft_id}/save-and-recheck", response_model=DraftRecheckResponse)
def save_and_recheck(
    draft_id: int,
    body: DraftSaveRequest,
    x_actor: Optional[str] = Header(default=None, alias="X-Actor"),
) -> DraftRecheckResponse:
    """Save draft, run deterministic + LLM conflict checks, update status."""
    actor = _resolve_actor(body.actor, x_actor)
    db = Database()
    try:
        result = save_and_recheck_draft(
            db,
            draft_id,
            body.full_text.strip(),
            actor,
        )
        raw_diff = result.get("clause_diff", {})
        return DraftRecheckResponse(
            draft=_to_draft_summary(result["draft"]),
            template_check=result["template_check"],
            glossary_check=result["glossary_check"],
            conflict_check=result["conflict_check"],
            clause_diff=ClauseDiffResult(
                added=raw_diff.get("added", []),
                modified=raw_diff.get("modified", []),
                unchanged=raw_diff.get("unchanged", []),
                has_changes=raw_diff.get("has_changes", False),
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Save-and-recheck failed for %s: %s", draft_id, exc)
        raise HTTPException(status_code=502, detail=f"Save and recheck failed: {exc}") from exc
    finally:
        db.close()



@router.get("/{draft_id}/versions", response_model=list[VersionHistoryItem])
def get_draft_versions(draft_id: int) -> list[VersionHistoryItem]:
    """Fetch all version history rows for a draft with GitHub-style + / - stats."""
    db = Database()
    try:
        draft = db.get_draft_document(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
        rows = db.get_gr_versions_history(draft_id)
        res = []
        for r in rows:
            created_at = r.get("created_at")
            res.append(
                VersionHistoryItem(
                    id=int(r["id"]),
                    gr_document_id=int(r["gr_document_id"]),
                    version_number=int(r["version_number"]),
                    full_text=r["full_text"],
                    actor=r.get("actor") or "anonymous",
                    lines_added=int(r.get("lines_added") or 0),
                    lines_deleted=int(r.get("lines_deleted") or 0),
                    chars_added=int(r.get("chars_added") or 0),
                    chars_deleted=int(r.get("chars_deleted") or 0),
                    raw_diff=r.get("raw_diff"),
                    created_at=str(created_at) if created_at else None,
                )
            )
        return res
    finally:
        db.close()


@router.get("/{draft_id}/versions/{version_number}", response_model=VersionHistoryItem)
def get_draft_version(draft_id: int, version_number: int) -> VersionHistoryItem:
    """Fetch details of a specific version number."""
    db = Database()
    try:
        row = db.get_gr_version_by_number(draft_id, version_number)
        if not row:
            raise HTTPException(
                status_code=404, detail=f"Version {version_number} for draft {draft_id} not found."
            )
        created_at = row.get("created_at")
        return VersionHistoryItem(
            id=int(row["id"]),
            gr_document_id=int(row["gr_document_id"]),
            version_number=int(row["version_number"]),
            full_text=row["full_text"],
            actor=row.get("actor") or "anonymous",
            lines_added=int(row.get("lines_added") or 0),
            lines_deleted=int(row.get("lines_deleted") or 0),
            chars_added=int(row.get("chars_added") or 0),
            chars_deleted=int(row.get("chars_deleted") or 0),
            raw_diff=row.get("raw_diff"),
            created_at=str(created_at) if created_at else None,
        )
    finally:
        db.close()


@router.post("/{draft_id}/share")

def share_draft_with_department(
    draft_id: int,
    user_name: Optional[str] = Query("Drafting Officer"),
) -> dict:
    """Share draft GR with department for employee review and Q&A."""
    db = Database()
    try:
        draft = db.get_draft_document(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
        db.share_draft_with_dept(draft_id, user_name=user_name or "Drafting Officer")
        # Post initial system comment
        db.add_gr_comment(
            gr_document_id=draft_id,
            user_name="System",
            user_role="System Bot",
            user_department=draft.get("department") or "General Administration Dept",
            comment_type="system_note",
            content=f"GR Draft version {draft.get('version_number', 1)} shared with department for Q&A and employee review by {user_name}.",
        )
        return {"status": "ok", "draft_id": draft_id, "shared_with_dept": True}
    finally:
        db.close()


@router.post("/{draft_id}/unshare")
def unshare_draft_from_department(draft_id: int) -> dict:
    """Unshare draft GR from department view."""
    db = Database()
    try:
        draft = db.get_draft_document(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
        db.unshare_draft_with_dept(draft_id)
        return {"status": "ok", "draft_id": draft_id, "shared_with_dept": False}
    finally:
        db.close()


@router.get("/{draft_id}/pdf")
@router.post("/{draft_id}/pdf")
def export_draft_as_pdf(draft_id: int):
    """Directly export GR draft as a formatted PDF file with government letterhead."""
    from fastapi.responses import Response as FastAPIResponse
    from services.pdf_export import generate_gr_pdf

    db = Database()
    try:
        draft = db.get_draft_document(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")

        tmpl = db.get_pdf_template()
        approval_notes = db.get_approval_notes(draft_id)
        pdf_bytes = generate_gr_pdf(draft, tmpl, approval_notes)

        clean_name = (draft.get("filename") or f"GR_{draft_id}").replace(".txt", "").replace(".pdf", "")
        filename = f"{clean_name}.pdf"

        return FastAPIResponse(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Export-Type": "pdf",
                "Access-Control-Expose-Headers": "Content-Disposition, X-Export-Type",
            },
        )
    finally:
        db.close()


@router.post("/{draft_id}/finalize")
def finalize_draft_and_export(draft_id: int):
    """Export GR draft as PDF."""
    return export_draft_as_pdf(draft_id)



@router.post("/{draft_id}/banish")
def banish_draft_from_forum(draft_id: int):
    """Explicitly banish / remove a finalized or approved GR draft from the Department Forum dashboard."""
    db = Database()
    try:
        draft = db.get_draft_document(draft_id)
        if not draft:
            raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found.")
        db.finalize_draft(draft_id)
        return {"status": "ok", "draft_id": draft_id, "banished": True, "shared_with_dept": False}
    finally:
        db.close()



