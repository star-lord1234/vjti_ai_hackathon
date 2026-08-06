"""Shared helpers for parsing JSON from local LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any, Dict


def clean_json_text(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def extract_json_object(text: str) -> Dict[str, Any]:
    """
    Parse JSON from an LLM response, tolerating markdown fences or leading prose.
    Raises json.JSONDecodeError when no object can be recovered.
    """
    cleaned = clean_json_text(text)
    if cleaned:
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        return json.loads(match.group(0))

    raise json.JSONDecodeError("Expecting value", text, 0)
