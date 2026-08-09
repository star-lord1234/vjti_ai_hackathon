"""
FastAPI router for PDF Template management (Admin only).
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from database.db import Database

router = APIRouter(prefix="/template", tags=["template"])


class TemplateUpdateRequest(BaseModel):
    department: Optional[str] = None
    header_line: Optional[str] = None
    footer_text: Optional[str] = None
    font_family: Optional[str] = None
    margins_pt: Optional[int] = None
    logo_base64: Optional[str] = None


@router.get("", response_model=Dict[str, Any])
def get_template():
    """Fetch the current PDF letterhead template."""
    db = Database()
    try:
        tmpl = db.get_pdf_template()
        if not tmpl:
            raise HTTPException(status_code=404, detail="No template configured.")
        return tmpl
    finally:
        db.close()


@router.put("", response_model=Dict[str, Any])
def update_template(body: TemplateUpdateRequest):
    """Admin: Update the PDF letterhead template fields."""
    db = Database()
    try:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=422, detail="No update fields provided.")
        return db.upsert_pdf_template(updates)
    finally:
        db.close()


@router.get("/preview")
def preview_template():
    """Admin: Generate a preview PDF of the current template with dummy text."""
    db = Database()
    try:
        from services.pdf_export import generate_gr_pdf

        tmpl = db.get_pdf_template()
        dummy_doc = {
            "id": 0,
            "filename": "preview_gr.txt",
            "gr_number_canonical": "GR/HTE/2026/PREVIEW",
            "gr_date": "09 ऑगस्ट 2026",
            "subject_mr": "हे एक नमुना शासन निर्णय आहे (Template Preview)",
            "full_text": (
                "१. राज्यातील सर्व मान्यताप्राप्त शासकीय महाविद्यालयात अराखीव प्रवर्गातील "
                "विद्यार्थ्यांना ५०% शिक्षण शुल्क माफी लागू राहील.\n\n"
                "२. पालकांचे वार्षिक उत्पन्न मर्यादा रुपये ८.०० लाख पेक्षा जास्त नसावे.\n\n"
                "३. या योजनेचा लाभ घेण्यासाठी विद्यार्थ्याने महाडीबीटी पोर्टलवर ऑनलाईन अर्ज करणे बंधनकारक राहील."
            ),
        }
        dummy_approvals = [
            {"user_name": "Dr. Rajesh V. Patil", "user_role": "Joint Secretary / Approver"},
        ]
        pdf_bytes = generate_gr_pdf(dummy_doc, tmpl, dummy_approvals)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": "inline; filename=template_preview.pdf"},
        )
    finally:
        db.close()
