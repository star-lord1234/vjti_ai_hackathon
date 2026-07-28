from __future__ import annotations

from typing import Any, Optional, List

from pydantic import BaseModel, Field, field_validator


class Reference(BaseModel):
    """
    One item under the 'वाचा' section.

    We keep it raw for now.
    Later the resolver will connect it to another GR.
    """

    raw: str
    date: Optional[str] = None


class GRMetadata(BaseModel):
    """
    Raw metadata extracted by the LLM.

    IMPORTANT:
    This model stores ONLY what the LLM returns.
    No normalization happens here.
    """

    filename: Optional[str] = None

    document_type: Optional[str] = None

    department: Optional[str] = None

    gr_number: Optional[str] = None

    # Filled after extraction (not by the LLM): uniform digits/spacing/OCR fixes
    gr_normalised: Optional[str] = None

    date: Optional[str] = None

    subject: Optional[str] = None

    references: List[Reference] = Field(default_factory=list)

    @field_validator("references", mode="before")
    @classmethod
    def coerce_references(cls, value: Any):
        if value is None:
            return []

        if not isinstance(value, list):
            value = [value]

        cleaned = []

        for item in value:
            if item is None:
                continue

            if isinstance(item, str):
                text = item.strip()
                if text:
                    cleaned.append({"raw": text})
                continue

            if isinstance(item, dict):
                raw = (
                    item.get("raw")
                    or item.get("text")
                    or item.get("reference")
                    or item.get("value")
                )
                if raw is None:
                    continue
                raw = str(raw).strip()
                if not raw:
                    continue
                date = item.get("date")
                cleaned.append(
                    {
                        "raw": raw,
                        "date": date if date not in ("", None) else None,
                    }
                )
                continue

            cleaned.append(item)

        return cleaned
