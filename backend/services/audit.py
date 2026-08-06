"""Centralized audit logging for draft workflow events."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from database.db import Database


def log_action(
    db: Database,
    gr_document_id: int,
    actor: str,
    action_type: str,
    finding_snapshot: Optional[Dict[str, Any]] = None,
    diff: Optional[str] = None,
    *,
    commit: bool = True,
) -> Dict[str, Any]:
    """
    Insert one audit_log row and optionally commit the transaction.
    Returns the inserted row as a dict.
    """
    snapshot_json = (
        json.dumps(finding_snapshot, ensure_ascii=False) if finding_snapshot is not None else None
    )
    db.cur.execute(
        """
        INSERT INTO audit_log (
            gr_document_id, actor, action_type, finding_snapshot, diff
        )
        VALUES (%s, %s, %s, %s::jsonb, %s)
        RETURNING id, gr_document_id, actor, action_type, finding_snapshot, diff, created_at
        """,
        (gr_document_id, actor, action_type, snapshot_json, diff),
    )
    row = db.cur.fetchone()
    cols = [desc[0] for desc in db.cur.description]
    record = dict(zip(cols, row))
    if record.get("created_at") is not None:
        record["created_at"] = str(record["created_at"])
    if isinstance(record.get("finding_snapshot"), str):
        try:
            record["finding_snapshot"] = json.loads(record["finding_snapshot"])
        except json.JSONDecodeError:
            pass
    if commit:
        db.conn.commit()
    return record
