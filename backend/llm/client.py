"""HTTP client for local Ollama (OpenAI-compatible /v1/chat/completions)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from llm.config import ollama_base_url


@dataclass
class _ChatMessage:
    content: str


@dataclass
class _ChatChoice:
    message: _ChatMessage


@dataclass
class _ChatCompletion:
    choices: List[_ChatChoice]


class _ChatCompletions:
    def __init__(self, base_url: str, http: httpx.Client) -> None:
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._http = http

    def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        **_: Any,
    ) -> _ChatCompletion:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format and response_format.get("type") == "json_object":
            payload["response_format"] = {"type": "json_object"}

        response = self._http.post(self._url, json=payload)
        response.raise_for_status()
        data = response.json()
        content = ""
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
        return _ChatCompletion(choices=[_ChatChoice(message=_ChatMessage(content=content))])


class _ChatAPI:
    def __init__(self, base_url: str, http: httpx.Client) -> None:
        self.completions = _ChatCompletions(base_url, http)


class OllamaChatClient:
    """Minimal OpenAI-shaped client backed by httpx (no openai package required)."""

    def __init__(self) -> None:
        base_url = ollama_base_url()
        if not base_url.endswith("/v1"):
            base_url = f"{base_url.rstrip('/')}/v1"
        self._base_url = base_url
        # trust_env=False — avoid system proxy breaking localhost when WiFi is off
        self._http = httpx.Client(
            trust_env=False,
            timeout=httpx.Timeout(600.0, connect=15.0),
        )
        self.chat = _ChatAPI(base_url, self._http)


def create_chat_client() -> OllamaChatClient:
    """Build a chat-completions client pointed at the local Ollama server."""
    return OllamaChatClient()
