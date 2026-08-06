"""Draft save / recheck business logic."""

from __future__ import annotations

import difflib
from typing import Any, Dict, Optional, Tuple

from database.db import Database
from reasoning.analyze_models import ConflictCheckSection
from reasoning.glossary import run_glossary_check
from reasoning.glossary.models import GlossaryCheckSection
from reasoning.llm_reasoner import check_conflict
from reasoning.models import ConflictFinding
from reasoning.template import run_template_check
from reasoning.template.models import TemplateCheckSection
from services.audit import log_action

DraftStatus = str  # draft | ready_for_approval | approved


def normalize_draft_text(text: str) -> str:
    """Normalize line endings and surrounding whitespace for comparisons."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def texts_equal(previous_text: str, new_text: str) -> bool:
    return normalize_draft_text(previous_text) == normalize_draft_text(new_text)


def compute_text_diff(previous_text: str, new_text: str) -> str:
    """Unified diff between the previous saved draft and the new content."""
    if texts_equal(previous_text, new_text):
        return ""

    previous_lines = normalize_draft_text(previous_text).splitlines(keepends=True)
    new_lines = normalize_draft_text(new_text).splitlines(keepends=True)
    diff_lines = difflib.unified_diff(
        previous_lines,
        new_lines,
        fromfile="previous",
        tofile="current",
        lineterm="",
    )
    return "\n".join(diff_lines)


def run_deterministic_checks(draft_text: str) -> Tuple[GlossaryCheckSection, TemplateCheckSection]:
    glossary_check = run_glossary_check(draft_text)
    template_check = run_template_check(draft_text)
    return glossary_check, template_check


def has_high_severity_findings(
    *,
    template_check: TemplateCheckSection,
    glossary_check: GlossaryCheckSection,
    conflict_result: Optional[ConflictFinding] = None,
) -> bool:
    """Return True when any high-severity issue blocks ready_for_approval."""
    if conflict_result is not None and conflict_result.conflicting:
        return True

    for violation in template_check.violations:
        if violation.severity == "high":
            return True

    for finding in template_check.findings:
        if finding.severity == "high":
            return True

    for finding in glossary_check.findings:
        if finding.confidence >= 0.9:
            return True

    return False


def _build_finding_snapshot(
    *,
    version_number: int,
    template_check: TemplateCheckSection,
    glossary_check: GlossaryCheckSection,
    conflict_result: Optional[ConflictFinding] = None,
    conflict_error: Optional[str] = None,
) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {
        "version_number": version_number,
        "template_check": template_check.model_dump(),
        "glossary_check": glossary_check.model_dump(),
    }
    if conflict_result is not None:
        snapshot["conflict_check"] = conflict_result.model_dump()
    elif conflict_error:
        snapshot["conflict_check"] = {"status": "error", "reason": conflict_error}
    return snapshot


def _persist_version_if_changed(
    db: Database,
    gr_document_id: int,
    full_text: str,
) -> Tuple[int, bool, str]:
    """
    Insert a new gr_versions row only when text changed.
    Returns (version_number, changed, previous_text).
    """
    draft = db.get_draft_document(gr_document_id)
    if not draft:
        raise ValueError(f"Draft document {gr_document_id} not found.")

    previous_text = draft.get("full_text") or draft.get("ocr_text") or ""
    current_version = int(draft.get("version_number") or 1)

    if texts_equal(previous_text, full_text):
        return current_version, False, previous_text

    version_number = db.get_next_version_number(gr_document_id)
    db.insert_gr_version(gr_document_id, version_number, full_text)
    return version_number, True, previous_text


def record_ai_analysis(
    db: Database,
    gr_document_id: int,
    actor: str,
    *,
    version_number: int,
    template_check: TemplateCheckSection,
    glossary_check: GlossaryCheckSection,
    conflict_result: Optional[ConflictFinding] = None,
    conflict_error: Optional[str] = None,
    commit: bool = True,
) -> Dict[str, Any]:
    """Log automated analysis results for a draft version."""
    snapshot = _build_finding_snapshot(
        version_number=version_number,
        template_check=template_check,
        glossary_check=glossary_check,
        conflict_result=conflict_result,
        conflict_error=conflict_error,
    )
    return log_action(
        db,
        gr_document_id,
        actor,
        "ai_suggestion",
        finding_snapshot=snapshot,
        diff=None,
        commit=commit,
    )


def save_draft_version(
    db: Database,
    gr_document_id: int,
    full_text: str,
    actor: str,
) -> Dict[str, Any]:
    """
    Persist a new draft version when text changed, audit edits/analysis, run deterministic checks.
    Always leaves status as draft.
    """
    version_number, changed, previous_text = _persist_version_if_changed(
        db, gr_document_id, full_text
    )
    db.update_draft_text_and_status(gr_document_id, full_text, "draft")

    glossary_check, template_check = run_deterministic_checks(full_text)
    snapshot = _build_finding_snapshot(
        version_number=version_number,
        template_check=template_check,
        glossary_check=glossary_check,
    )

    if changed:
        audit_row = log_action(
            db,
            gr_document_id,
            actor,
            "human_edit",
            finding_snapshot=snapshot,
            diff=compute_text_diff(previous_text, full_text) or None,
            commit=False,
        )
    else:
        audit_row = record_ai_analysis(
            db,
            gr_document_id,
            actor,
            version_number=version_number,
            template_check=template_check,
            glossary_check=glossary_check,
            commit=False,
        )

    db.conn.commit()

    updated = db.get_draft_document(gr_document_id)
    return {
        "draft": updated,
        "version_number": version_number,
        "version_changed": changed,
        "status": "draft",
        "template_check": template_check,
        "glossary_check": glossary_check,
        "audit_id": audit_row["id"],
    }


def save_and_recheck_draft(
    db: Database,
    gr_document_id: int,
    full_text: str,
    actor: str,
) -> Dict[str, Any]:
    """
    Save draft version when text changed, run deterministic + LLM conflict checks, update status.
    """
    version_number, changed, previous_text = _persist_version_if_changed(
        db, gr_document_id, full_text
    )

    glossary_check, template_check = run_deterministic_checks(full_text)

    conflict_section: ConflictCheckSection
    conflict_result: Optional[ConflictFinding] = None
    conflict_error: Optional[str] = None
    try:
        conflict_result = check_conflict(full_text, db=db)
        conflict_section = ConflictCheckSection(status="ok", result=conflict_result)
    except Exception as exc:
        conflict_error = str(exc)
        conflict_section = ConflictCheckSection(status="error", reason=conflict_error)

    has_high = has_high_severity_findings(
        template_check=template_check,
        glossary_check=glossary_check,
        conflict_result=conflict_result if conflict_section.status == "ok" else None,
    )

    status: DraftStatus = "draft" if has_high else "ready_for_approval"
    db.update_draft_text_and_status(gr_document_id, full_text, status)

    snapshot = _build_finding_snapshot(
        version_number=version_number,
        template_check=template_check,
        glossary_check=glossary_check,
        conflict_result=conflict_result if conflict_section.status == "ok" else None,
        conflict_error=conflict_error,
    )

    if changed:
        log_action(
            db,
            gr_document_id,
            actor,
            "human_edit",
            finding_snapshot=snapshot,
            diff=compute_text_diff(previous_text, full_text) or None,
            commit=False,
        )

    record_ai_analysis(
        db,
        gr_document_id,
        actor,
        version_number=version_number,
        template_check=template_check,
        glossary_check=glossary_check,
        conflict_result=conflict_result if conflict_section.status == "ok" else None,
        conflict_error=conflict_error,
        commit=False,
    )

    if status == "ready_for_approval":
        log_action(
            db,
            gr_document_id,
            actor,
            "submitted_for_review",
            finding_snapshot=snapshot,
            commit=True,
        )
    else:
        db.conn.commit()

    updated = db.get_draft_document(gr_document_id)
    return {
        "draft": updated,
        "version_number": version_number,
        "version_changed": changed,
        "status": status,
        "template_check": template_check,
        "glossary_check": glossary_check,
        "conflict_check": conflict_section,
    }
