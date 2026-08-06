"""Tests for LLM JSON parsing helpers."""

from __future__ import annotations

import json

import pytest

from reasoning.json_utils import extract_json_object


def test_extract_json_object_plain():
    parsed = extract_json_object('{"ok": true}')
    assert parsed == {"ok": True}


def test_extract_json_object_markdown_fence():
    parsed = extract_json_object('```json\n{"findings": []}\n```')
    assert parsed == {"findings": []}


def test_extract_json_object_raises_on_empty():
    with pytest.raises(json.JSONDecodeError):
        extract_json_object("")
