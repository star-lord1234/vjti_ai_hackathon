"""Glossary checker-specific exceptions."""


class GlossaryCheckUnavailable(Exception):
    """Raised when the local LLM client is on cooldown — expected degradation, not a bug."""

    def __init__(self, reason: str = "llm_unavailable") -> None:
        self.reason = reason
        super().__init__(reason)
