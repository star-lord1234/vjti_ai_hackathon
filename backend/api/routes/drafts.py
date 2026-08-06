"""Editable draft lifecycle endpoints with audit trail."""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
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


class DraftRecheckResponse(DraftSaveResponse):
    conflict_check: ConflictCheckSection


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
        return DraftRecheckResponse(
            draft=_to_draft_summary(result["draft"]),
            template_check=result["template_check"],
            glossary_check=result["glossary_check"],
            conflict_check=result["conflict_check"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Save-and-recheck failed for %s: %s", draft_id, exc)
        raise HTTPException(status_code=502, detail=f"Save and recheck failed: {exc}") from exc
    finally:
        db.close()
