"""Singleton manager for the local Ollama chat client."""

from __future__ import annotations

import time
import threading
from typing import Any, Optional, Tuple

from llm.client import create_chat_client
from llm.config import ollama_base_url, ollama_model


class LLMClientManager:
    """Provides round-robin access to a single local Ollama client with optional cooldown."""

    def __init__(self) -> None:
        self.clients = [create_chat_client()]
        self.cooldown_until = [0.0]
        self.current = 0
        self.lock = threading.Lock()
        print(f"Using local Ollama ({ollama_model()}) at {ollama_base_url()}.")

    def get_client(self) -> Tuple[Optional[int], Optional[Any]]:
        with self.lock:
            now = time.time()
            idx = self.current
            self.current = (self.current + 1) % len(self.clients)
            if now >= self.cooldown_until[idx]:
                return idx, self.clients[idx]
            return None, None

    def seconds_until_available(self) -> float:
        with self.lock:
            now = time.time()
            wait = min(self.cooldown_until) - now
            return max(0.0, wait)

    def wait_for_client(
        self, poll: float = 0.25, max_wait: Optional[float] = None
    ) -> Tuple[Optional[int], Optional[Any]]:
        started = time.time()
        while True:
            idx, client = self.get_client()
            if client is not None:
                return idx, client
            if max_wait is not None and (time.time() - started) >= max_wait:
                return None, None
            wait = self.seconds_until_available()
            sleep_for = poll if not wait else max(poll, min(wait, 2.0))
            if max_wait is not None:
                sleep_for = min(sleep_for, max(0.0, max_wait - (time.time() - started)))
            time.sleep(sleep_for)

    def mark_rate_limited(
        self,
        idx: int,
        retry_after: Optional[float] = None,
        default_cooldown: float = 60,
        all_keys: bool = False,
    ) -> None:
        with self.lock:
            try:
                cooldown = (
                    float(retry_after) if retry_after is not None else float(default_cooldown)
                )
            except (TypeError, ValueError):
                cooldown = float(default_cooldown)
            cooldown = max(1.0, cooldown) + 0.35
            until = time.time() + cooldown
            if all_keys:
                for i in range(len(self.clients)):
                    self.cooldown_until[i] = max(self.cooldown_until[i], until)
                print(f"\nLLM client cooling for {cooldown:.1f}s.")
            else:
                self.cooldown_until[idx] = max(self.cooldown_until[idx], until)
                print(f"\nLLM client cooling for {cooldown:.1f}s.")

    def print_status(self) -> None:
        with self.lock:
            now = time.time()
            remaining = max(0, int(self.cooldown_until[0] - now))
            status = "READY" if remaining == 0 else f"Cooldown ({remaining}s)"
            print(f"\n========== Ollama LLM ==========\nClient: {status}\n==============================\n")
