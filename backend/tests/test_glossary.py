"""Unit tests for glossary terminology checker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from reasoning.glossary.checker import run_glossary_check
from reasoning.glossary.exceptions import GlossaryCheckUnavailable
from reasoning.glossary.loader import GLOSSARY_ENTRIES, get_glossary_for_prompt
from reasoning.glossary.models import GlossaryFinding, GlossaryLLMOutput


def test_glossary_loaded_at_init():
    assert len(GLOSSARY_ENTRIES) >= 40
    assert all(entry.id for entry in GLOSSARY_ENTRIES)


def test_glossary_prompt_includes_entries():
    prompt = get_glossary_for_prompt()
    assert "government_resolution" in prompt
    assert "शासन निर्णय" in prompt


def test_empty_draft_returns_ok_without_llm():
    result = run_glossary_check("   ")
    assert result.status == "ok"
    assert result.findings == []


def test_unavailable_when_no_api_keys():
    mock_mgr = MagicMock()
    mock_mgr.get_client.return_value = (None, None)

    with patch("reasoning.glossary.checker.GLOSSARY_USE_LLM", True):
        with patch("reasoning.glossary.checker.get_llm_manager", return_value=mock_mgr):
            result = run_glossary_check("सक्षम अधिकारी मंजूर करण्यात येत आहे.")

    assert result.status == "unavailable"
    assert result.reason == "llm_unavailable"
    assert result.findings == []


def test_ok_when_llm_returns_findings():
    mock_mgr = MagicMock()
    mock_client = MagicMock()
    mock_mgr.get_client.return_value = (0, mock_client)

    llm_payload = GlossaryLLMOutput(
        findings=[
            GlossaryFinding(
                text_found="सक्षम अधिकारी",
                context_snippet="सक्षम अधिकारी मंजूर करण्यात येत आहे",
                canonical_term="सक्षम प्राधिकरण",
                reason="Use formal term for operative clauses",
                confidence=0.92,
            )
        ]
    )
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content=llm_payload.model_dump_json()))]
    mock_client.chat.completions.create.return_value = mock_completion

    with patch("reasoning.glossary.checker.GLOSSARY_USE_LLM", True):
        with patch("reasoning.glossary.checker.get_llm_manager", return_value=mock_mgr):
            result = run_glossary_check("सक्षम अधिकारी मंजूर करण्यात येत आहे.")

    assert result.status == "ok"
    assert len(result.findings) == 1
    assert result.findings[0].canonical_term == "सक्षम प्राधिकरण"


def test_deterministic_scan_finds_variant():
    result = run_glossary_check("सक्षम अधिकारी मंजूर करण्यात येत आहे.")
    assert result.status == "ok"
    assert len(result.findings) >= 1
    assert any(f.text_found == "सक्षम अधिकारी" for f in result.findings)


def test_require_available_client_raises():
    from reasoning.glossary.checker import _require_available_client

    mock_mgr = MagicMock()
    mock_mgr.get_client.return_value = (None, None)

    with pytest.raises(GlossaryCheckUnavailable) as exc_info:
        _require_available_client(mock_mgr)

    assert exc_info.value.reason == "llm_unavailable"
