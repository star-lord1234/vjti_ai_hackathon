"""
Offline-first environment bootstrap.

Conflict detection needs:
  1. Local Ollama (localhost) — no internet
  2. Cached Hugging Face embedding weights — no hub calls when WiFi is off
  3. Local Postgres + Neo4j

Call ``configure_offline_mode()`` as early as possible in process startup.
"""

from __future__ import annotations

import os


def _truthy(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def configure_offline_mode() -> None:
    """Prevent Hugging Face hub/network calls when the embedding model is cached locally."""
    if _truthy("EMBEDDING_LOCAL_FILES_ONLY", "true"):
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
