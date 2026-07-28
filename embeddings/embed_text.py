import os
from typing import Optional

DEFAULT_MAX_OCR_CHARS = 500


def build_embedding_text(row: dict, max_ocr_chars: Optional[int] = None) -> str:
    """
    Build compact text to embed from a gr_documents row.
    Combines subject_mr + department + gr_number_canonical + truncated prefix of ocr_text.
    """

    if max_ocr_chars is None:
        max_ocr_chars = int(
            os.getenv("EMBEDDING_MAX_OCR_CHARS", str(DEFAULT_MAX_OCR_CHARS))
        )

    parts = []

    subject = row.get("subject_mr")
    if subject and str(subject).strip():
        parts.append(str(subject).strip())

    department = row.get("department")
    if department and str(department).strip():
        parts.append(str(department).strip())

    gr_number = row.get("gr_number_canonical")
    if gr_number and str(gr_number).strip():
        parts.append(str(gr_number).strip())

    ocr_text = row.get("ocr_text")
    if ocr_text and str(ocr_text).strip():
        truncated_ocr = str(ocr_text).strip()[:max_ocr_chars]
        if truncated_ocr:
            parts.append(truncated_ocr)

    return "\n".join(parts)
