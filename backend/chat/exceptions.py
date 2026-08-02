"""Chat-specific exceptions (isolated from analysis APIManager)."""


class ChatUnavailable(Exception):
    """Chat Groq key is rate-limited or exhausted."""

    def __init__(self, reason: str = "api_quota_exhausted") -> None:
        self.reason = reason
        super().__init__(reason)


class ChatRateLimited(Exception):
    """In-memory per-session message rate limit exceeded."""

    def __init__(self, reason: str = "rate_limit_exceeded") -> None:
        self.reason = reason
        super().__init__(reason)
