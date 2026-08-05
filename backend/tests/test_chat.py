"""Unit tests for isolated draft chat service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from chat.models import ChatMessageRequest
from chat.service import handle_chat_message


def test_no_document_skips_llm():
    result = handle_chat_message(
        ChatMessageRequest(message="What is section 4?", draft_text="   ")
    )
    assert result.status == "no_document"
    assert result.reason == "no_draft_loaded"


def test_ok_reply_from_isolated_client():
    mock_client = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(message=MagicMock(content="Section 4 covers jurisdiction."))
    ]
    mock_client.chat.completions.create.return_value = mock_completion

    with patch("chat.service._get_chat_client", return_value=mock_client):
        with patch("chat.service._require_chat_available"):
            result = handle_chat_message(
                ChatMessageRequest(
                    message="What does section 4 say?",
                    draft_text="कलम 4 — अधिकारक्षेत्र\n4.1 विभाग हा नोडल विभाग राहील.",
                    session_id="test-session-1",
                )
            )

    assert result.status == "ok"
    assert "jurisdiction" in (result.reply or "").lower() or "Section 4" in (result.reply or "")


def test_unavailable_on_rate_limit():
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("429 rate limit exceeded")

    with patch("chat.service._get_chat_client", return_value=mock_client):
        with patch("chat.service._require_chat_available"):
            result = handle_chat_message(
                ChatMessageRequest(
                    message="Summarize",
                    draft_text="विषय: चाचणी\nकलम 1 तरतूद.",
                    session_id="test-session-2",
                )
            )

    assert result.status == "unavailable"
    assert result.reason == "llm_unavailable"
