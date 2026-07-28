"""
Document detail and list endpoints router.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.db import Database
from graph.neo4j_query import Neo4jReader

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=Dict[str, Any])
def list_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    department: Optional[str] = Query(None, description="Department filter"),
    search: Optional[str] = Query(None, description="Search query on subject or GR number"),
) -> Dict[str, Any]:
    """
    List and paginate GR documents with optional department and search filters.
    Does not return heavy ocr_text payload.
    """
    db = Database()
    try:
        return db.get_paginated_documents(
            page=page,
            page_size=page_size,
            department=department,
            search=search,
        )
    finally:
        db.close()


@router.get("/{gr_id}", response_model=Dict[str, Any])
def get_document_by_id(gr_id: int) -> Dict[str, Any]:
    """
    Fetch full document detail by ID including ocr_text and raw citations JSONB.
    """
    db = Database()
    try:
        doc = db.get_by_id(gr_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document with ID {gr_id} not found.")
        return doc
    finally:
        db.close()


@router.get("/{gr_id}/citations", response_model=Dict[str, Any])
def get_document_citations(gr_id: int) -> Dict[str, Any]:
    """
    Fetch citations for a GR document:
    returns raw citations array from Postgres and resolved Neo4j CITES target GRs.
    """
    db = Database()
    try:
        doc = db.get_by_id(gr_id)
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document with ID {gr_id} not found.")

        raw_citations = doc.get("citations") or []

        resolved_targets: List[Dict[str, Any]] = []
        try:
            with Neo4jReader() as reader:
                resolved_targets = reader.get_cites_edges(gr_id)
        except Exception:
            resolved_targets = []

        return {
            "gr_id": gr_id,
            "gr_number_canonical": doc.get("gr_number_canonical"),
            "raw_citations": raw_citations,
            "resolved_targets": resolved_targets,
        }
    finally:
        db.close()
