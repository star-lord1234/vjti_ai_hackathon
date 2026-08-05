"""Chat-specific exceptions (isolated from analysis LLMClientManager)."""


class ChatUnavailable(Exception):
    """Local LLM is unavailable or cooling down."""

    def __init__(self, reason: str = "llm_unavailable") -> None:
        self.reason = reason
        super().__init__(reason)


class ChatRateLimited(Exception):
    """In-memory per-session message rate limit exceeded."""

    def __init__(self, reason: str = "rate_limit_exceeded") -> None:
        self.reason = reason
        super().__init__(reason)
