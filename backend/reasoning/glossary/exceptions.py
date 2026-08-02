"""Glossary checker-specific exceptions."""


class GlossaryCheckUnavailable(Exception):
    """Raised when all Groq API keys are on cooldown — expected degradation, not a bug."""

    def __init__(self, reason: str = "api_quota_exhausted") -> None:
        self.reason = reason
        super().__init__(reason)
