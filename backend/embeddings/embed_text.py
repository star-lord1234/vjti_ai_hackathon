import os
import re
from typing import List, Optional

DEFAULT_MAX_OCR_CHARS = 2000
DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150


def build_embedding_text(row: dict, max_ocr_chars: Optional[int] = None) -> str:
    """
    Build text to embed for a gr_documents row.
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
    else:
        # Add explicit metadata-only tag to prevent vector collisions for documents missing OCR
        filename = row.get("filename", "")
        parts.append(f"[NO OCR TEXT AVAILABLE - METADATA ONLY: {filename}]")

    return "\n".join(parts)


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """
    Split long text into overlapping chunks by paragraph or sliding window.
    """
    if not text or not text.strip():
        return []

    clean_text = text.strip()
    if len(clean_text) <= chunk_size:
        return [clean_text]

    # Split into paragraphs first
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n+", clean_text) if p.strip()]
    if not paragraphs:
        paragraphs = [clean_text]

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        # If single paragraph is longer than chunk_size, slide window over it
        if para_len > chunk_size:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            
            start = 0
            while start < para_len:
                end = min(start + chunk_size, para_len)
                sub_chunk = para[start:end].strip()
                if sub_chunk:
                    chunks.append(sub_chunk)
                if end >= para_len:
                    break
                start += chunk_size - overlap
            continue

        if current_len + para_len + 2 > chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            # Keep last paragraph for overlap if short enough
            if len(current_chunk[-1]) <= overlap:
                current_chunk = [current_chunk[-1], para]
                current_len = len(current_chunk[0]) + para_len + 2
            else:
                current_chunk = [para]
                current_len = para_len
        else:
            current_chunk.append(para)
            current_len += para_len + 2

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks
