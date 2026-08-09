"""Draft save / recheck business logic."""

from __future__ import annotations

import difflib
from typing import Any, Dict, Optional, Tuple

from database.db import Database
from reasoning.analyze_models import ConflictCheckSection
from reasoning.clause_parser import ClauseDiff, diff_clauses
from reasoning.glossary import run_glossary_check
from reasoning.glossary.models import GlossaryCheckSection
from reasoning.llm_reasoner import check_conflict
from reasoning.models import ConflictFinding
from reasoning.template import run_template_check
from reasoning.template.models import TemplateCheckSection
from services.audit import log_action

DraftStatus = str  # draft | ready_for_approval | approved


def normalize_draft_text(text: str) -> str:
    """
    Normalize line endings, strip per-line trailing whitespace, and strip surrounding whitespace.
    Prevents trailing space mismatches between PDF/OCR extraction and textarea editing.
    """
    if not text:
        return ""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    return "\n".join(line.rstrip() for line in lines).strip()


def texts_equal(previous_text: str, new_text: str) -> bool:
    return normalize_draft_text(previous_text) == normalize_draft_text(new_text)


def compute_text_diff(previous_text: str, new_text: str) -> str:
    """
    Unified line-level diff between the previous and new draft text.

    Uses ``keepends=False`` so trailing-newline differences between the last
    line of one version and the first/last line of another do not produce
    spurious ``-``/``+`` pairs for identical content.
    """
    if texts_equal(previous_text, new_text):
        return ""

    previous_lines = normalize_draft_text(previous_text).splitlines(keepends=False)
    new_lines = normalize_draft_text(new_text).splitlines(keepends=False)
    diff_lines = difflib.unified_diff(
        previous_lines,
        new_lines,
        fromfile="previous",
        tofile="current",
        lineterm="",
    )
    return "\n".join(diff_lines)


def compute_diff_stats(previous_text: str, current_text: str) -> Dict[str, Any]:
    """
    Compute GitHub-style diff metrics (+/- lines and characters) and unified diff patch.
    """
    prev_norm = normalize_draft_text(previous_text)
    curr_norm = normalize_draft_text(current_text)

    prev_lines = prev_norm.splitlines() if prev_norm else []
    curr_lines = curr_norm.splitlines() if curr_norm else []

    diff_lines = list(difflib.unified_diff(
        prev_lines,
        curr_lines,
        fromfile="previous",
        tofile="current",
        lineterm="",
    ))

    lines_added = 0
    lines_deleted = 0
    chars_added = 0
    chars_deleted = 0

    for line in diff_lines:
        if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            lines_added += 1
            chars_added += len(line[1:])
        elif line.startswith("-"):
            lines_deleted += 1
            chars_deleted += len(line[1:])

    raw_diff = "\n".join(diff_lines) if diff_lines else ""

    return {
        "lines_added": lines_added,
        "lines_deleted": lines_deleted,
        "chars_added": chars_added,
        "chars_deleted": chars_deleted,
        "raw_diff": raw_diff,
    }


def compute_clause_diff_text(previous_text: str, current_text: str) -> str:
    """
    Generate a human-readable clause-level diff for storage in ``audit_log.diff``.

    Format::

        ~ CLAUSE DIFF (v{n} → v{n+1})
        - 1. The scholarship shall be Rs. 5000 per year.   ← removed/changed
        + 1. The scholarship shall be Rs. 7000 per year.   ← added/changed
          2. Eligibility: Students from BPL families.      ← unchanged (space prefix)
          3. Application deadline: 31 March.               ← unchanged
        + 4. Renewal: Annual renewal required.             ← new clause

    Only clauses that genuinely changed get ``+``/``-`` markers.
    Unchanged clauses get a single-space prefix so they are visible in context
    but clearly not flagged as modifications.
    """
    from reasoning.clause_parser import diff_clauses, extract_draft_clauses

    prev_clauses = extract_draft_clauses(previous_text)
    curr_clauses = extract_draft_clauses(current_text)
    clause_diff = diff_clauses(previous_text, current_text)

    # Build a lookup of unchanged clause texts for O(1) checking
    unchanged_set = set(clause_diff.unchanged)

    lines = ["~ CLAUSE DIFF"]

    # Show removed/modified clauses from previous version that are no longer present
    # Build a content-hash set of current clauses for the removal detection
    from reasoning.clause_parser import _clause_hash
    curr_hashes = {_clause_hash(c) for c in curr_clauses}
    for clause in prev_clauses:
        if _clause_hash(clause) not in curr_hashes:
            lines.append(f"- {clause}")

    # Walk current clauses in order: unchanged → space prefix, changed → + prefix
    for clause in curr_clauses:
        if clause in unchanged_set:
            lines.append(f"  {clause}")
        else:
            lines.append(f"+ {clause}")

    return "\n".join(lines)


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
    actor: str = "anonymous",
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
    diff_stats = compute_diff_stats(previous_text, full_text)
    db.insert_gr_version(
        gr_document_id,
        version_number,
        full_text,
        actor=actor,
        lines_added=diff_stats["lines_added"],
        lines_deleted=diff_stats["lines_deleted"],
        chars_added=diff_stats["chars_added"],
        chars_deleted=diff_stats["chars_deleted"],
        raw_diff=diff_stats["raw_diff"],
    )
    if hasattr(db, "conn") and db.conn:
        db.conn.commit()
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
        db, gr_document_id, full_text, actor=actor
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
    Returns clause_diff so callers can surface which clauses actually changed.
    """
    version_number, changed, previous_text = _persist_version_if_changed(
        db, gr_document_id, full_text, actor=actor
    )

    # Compute clause-level diff so unchanged clauses are not flagged as new
    clause_diff: ClauseDiff = diff_clauses(previous_text, full_text)

    glossary_check, template_check = run_deterministic_checks(full_text)

    conflict_section: ConflictCheckSection
    conflict_result: Optional[ConflictFinding] = None
    conflict_error: Optional[str] = None
    try:
        conflict_result = check_conflict(full_text, top_k=15, hops=1, db=db)
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
    db.update_draft_text_and_status(gr_document_id, full_text, status, commit=True)


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
            commit=True,
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
        # Clause-level diff for incremental re-check UI and caching
        "clause_diff": {
            "added": clause_diff.added,
            "modified": clause_diff.modified,
            "unchanged": clause_diff.unchanged,
            "has_changes": clause_diff.has_changes,
        },
    }
