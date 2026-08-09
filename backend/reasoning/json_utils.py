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
    Parse JSON from an LLM response, tolerating markdown fences, trailing commas,
    missing object delimiters, or unescaped linebreaks.
    """
    cleaned = clean_json_text(text)
    if cleaned:
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Extract JSON string candidate block
    match = re.search(r"\{[\s\S]*\}", text)
    raw = match.group(0) if match else cleaned

    # Apply sequential syntax repairs for common LLM generation mistakes
    repairs = [
        raw,
        # Remove trailing commas before closing braces/brackets
        re.sub(r",\s*([\}\]])", r"\1", raw),
        # Add missing commas between adjacent objects: } { -> }, {
        re.sub(r"\}\s*\{", "},{", re.sub(r",\s*([\}\]])", r"\1", raw)),
        # Add missing commas between newlines: " \n "key" -> ", \n "key"
        re.sub(r'("\s*)\n(\s*")', r'\1,\n\2', re.sub(r",\s*([\}\]])", r"\1", raw)),
    ]

    for candidate in repairs:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    raise json.JSONDecodeError("Expecting value", text, 0)


