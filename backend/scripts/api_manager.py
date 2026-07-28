import os
import time
import threading
from pathlib import Path

from groq import Groq
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class APIManager:

    def __init__(self):

        self.clients = []
        self.cooldown_until = []

        # Automatically load GROQ_API_KEY_1, GROQ_API_KEY_2, ...
        i = 1

        while True:

            key = os.getenv(f"GROQ_API_KEY_{i}")

            if key is None:
                break

            key = key.strip()
            if key:
                self.clients.append(Groq(api_key=key))
                self.cooldown_until.append(0.0)

            i += 1

        if not self.clients:
            raise RuntimeError("No Groq API keys found.")

        self.current = 0

        self.lock = threading.Lock()

        print(f"Loaded {len(self.clients)} Groq API key(s).")

    # -------------------------------------------------------
    # Returns an available client using round-robin
    # -------------------------------------------------------

    def get_client(self):

        with self.lock:

            now = time.time()

            n = len(self.clients)

            for _ in range(n):

                idx = self.current

                self.current = (self.current + 1) % n

                if now >= self.cooldown_until[idx]:

                    return idx, self.clients[idx]

            return None, None

    def seconds_until_available(self):
        """How long until any key is ready (0 if one is ready now)."""

        with self.lock:

            now = time.time()
            wait = min(self.cooldown_until) - now
            return max(0.0, wait)

    def wait_for_client(self, poll=0.25, max_wait=None):
        """
        Block until a key is available, then return (idx, client).
        If max_wait is set and exceeded, return (None, None).
        """

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

    # -------------------------------------------------------
    # Mark key as cooling down
    # -------------------------------------------------------

    def mark_rate_limited(
        self,
        idx,
        retry_after=None,
        default_cooldown=60,
        all_keys=False,
    ):
        """
        Cool down one key, or all keys (shared-org TPD / RPM limits).
        """

        with self.lock:

            try:
                cooldown = float(retry_after) if retry_after is not None else float(default_cooldown)
            except (TypeError, ValueError):
                cooldown = float(default_cooldown)

            # Never cool for less than 1s; add a small buffer
            cooldown = max(1.0, cooldown) + 0.35
            until = time.time() + cooldown

            if all_keys:
                for i in range(len(self.clients)):
                    self.cooldown_until[i] = max(self.cooldown_until[i], until)
                print(f"\nAll keys cooling for {cooldown:.1f}s (shared limit).")
            else:
                self.cooldown_until[idx] = max(self.cooldown_until[idx], until)
                print(f"\nKey {idx + 1} cooling for {cooldown:.1f}s.")

    # -------------------------------------------------------
    # Optional helper
    # -------------------------------------------------------

    def print_status(self):

        with self.lock:

            now = time.time()

            print("\n========== API Keys ==========")

            for i in range(len(self.clients)):

                remaining = max(
                    0,
                    int(self.cooldown_until[i] - now)
                )

                if remaining == 0:

                    status = "READY"

                else:

                    status = f"Cooldown ({remaining}s)"

                print(
                    f"Key {i + 1}: {status}"
                )

            print("==============================\n")
