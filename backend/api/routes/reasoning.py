"""
AI Reasoning endpoints router (Q&A, pairwise GR comparison, conflict detection).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from reasoning.llm_reasoner import answer_query, check_conflict, compare_grs
from reasoning.models import ComparisonResult, ConflictFinding, QueryAnswer

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
    top_k: int = Field(15, ge=1, le=100, description="Vector top_k seeds")
    hops: int = Field(1, ge=0, le=5, description="Graph citation expansion hops")


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
