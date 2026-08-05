"""Backward-compatible shim — use ``llm.manager.LLMClientManager`` directly."""

from llm.manager import LLMClientManager as APIManager

__all__ = ["APIManager"]
