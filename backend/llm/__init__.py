"""Local Ollama LLM integration."""

from llm.client import create_chat_client
from llm.config import (
    default_chat_model,
    default_ingest_model,
    default_reasoning_model,
    ollama_base_url,
    ollama_model,
)
from llm.manager import LLMClientManager

__all__ = [
    "LLMClientManager",
    "create_chat_client",
    "default_chat_model",
    "default_ingest_model",
    "default_reasoning_model",
    "ollama_base_url",
    "ollama_model",
]
