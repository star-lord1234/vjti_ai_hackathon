"""Local Ollama LLM configuration."""

from __future__ import annotations

import os


def ollama_model() -> str:
    return os.getenv("OLLAMA_MODEL", "llama3.1").strip()


def ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").strip().rstrip("/")


def default_reasoning_model() -> str:
    return os.getenv("REASONING_MODEL", ollama_model())


def default_chat_model() -> str:
    return os.getenv("OLLAMA_CHAT_MODEL", ollama_model())


def default_ingest_model() -> str:
    return os.getenv("INGEST_LLM_MODEL", ollama_model())
