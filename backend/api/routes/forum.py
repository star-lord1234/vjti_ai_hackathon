"""
FastAPI router for Department Collaboration Forum & In-Progress GR Inspection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from database.db import Database

router = APIRouter(prefix="/forum", tags=["forum"])


class CreateCommentRequest(BaseModel):
    parent_id: Optional[int] = Field(None, description="Optional parent comment ID if answering/replying to a question")
    user_name: str = Field(..., description="Name of the posting user")
    user_role: str = Field(..., description="Role of the user (Drafting Officer, Reviewer, Approver)")
    user_department: Optional[str] = Field("General Administration Dept", description="Department of user")
    comment_type: str = Field("question", description="type: question, answer, review_comment, suggestion, approval_note")
    content: str = Field(..., min_length=2, description="Content of the comment/question/answer")


class ToggleResolutionRequest(BaseModel):
    is_resolved: bool = Field(..., description="Resolution status")


@router.get("/in-progress", response_model=List[Dict[str, Any]])
def list_in_progress_forum_grs():
    """Fetch all draft GRs currently shared with the department for employee review."""
    db = Database()
    try:
        return db.get_in_progress_forum_grs()
    finally:
        db.close()


@router.get("/{gr_id}", response_model=Dict[str, Any])
def get_shared_gr_detail(gr_id: int):
    """Fetch full read-only details of a shared GR draft including comments and approval status."""
    db = Database()
    try:
        doc = db.get_draft_document(gr_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GR draft not found")
        
        comments = db.get_gr_comments(gr_id)
        versions = db.get_gr_versions_history(gr_id)
        approval_notes = db.get_approval_notes(gr_id)
        is_approved = db.is_fully_approved(gr_id)

        
        return {
            "gr_document": doc,
            "comments": comments,
            "versions": versions,
            "approval_notes": approval_notes,
            "is_fully_approved": is_approved,
        }
    finally:
        db.close()


@router.post("/{gr_id}/comments", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
def post_gr_comment(gr_id: int, body: CreateCommentRequest):
    """Post a new question, review comment, or suggestion to a shared GR draft."""
    db = Database()
    try:
        doc = db.get_draft_document(gr_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GR draft not found")


        comment = db.add_gr_comment(
            gr_document_id=gr_id,
            user_name=body.user_name,
            user_role=body.user_role,
            user_department=body.user_department or "General Administration Dept",
            comment_type=body.comment_type,
            content=body.content,
            parent_id=body.parent_id,
        )
        return comment
    finally:
        db.close()



@router.get("/{gr_id}/comments", response_model=List[Dict[str, Any]])
def get_gr_comments(gr_id: int):
    """Fetch all comments/questions for a specific shared GR."""
    db = Database()
    try:
        return db.get_gr_comments(gr_id)
    finally:
        db.close()


@router.patch("/comments/{comment_id}/resolve", response_model=Dict[str, Any])
def toggle_comment_resolution(comment_id: int, body: ToggleResolutionRequest):
    """Toggle resolution status of a question/comment."""
    db = Database()
    try:
        db.toggle_comment_resolution(comment_id, body.is_resolved)
        return {"status": "ok", "comment_id": comment_id, "is_resolved": body.is_resolved}
    finally:
        db.close()
