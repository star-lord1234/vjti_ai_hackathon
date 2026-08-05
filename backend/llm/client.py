"""Create an OpenAI-compatible client for local Ollama."""

from __future__ import annotations

import os
from typing import Any

import httpx

from llm.config import ollama_base_url


def create_chat_client() -> Any:
    """Build a chat-completions client pointed at the local Ollama server."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Ollama integration requires the openai package. Run: pip install openai"
        ) from exc

    base_url = ollama_base_url()
    if not base_url.endswith("/v1"):
        base_url = f"{base_url.rstrip('/')}/v1"

    api_key = os.getenv("OLLAMA_API_KEY", "ollama")
    # trust_env=False — do not route localhost Ollama through system HTTP proxy when WiFi is off
    timeout = httpx.Timeout(600.0, connect=15.0)
    http_client = httpx.Client(trust_env=False, timeout=timeout)
    return OpenAI(base_url=base_url, api_key=api_key, http_client=http_client)
