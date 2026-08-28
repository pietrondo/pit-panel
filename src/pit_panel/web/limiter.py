import time

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


class RateLimiter:
    def __init__(self, requests: int, window: int):
        self.requests = requests
        self.window = window
        self._cache: dict[str, list[float]] = {}
        self._last_global_cleanup = time.monotonic()

    def is_allowed(self, key: str) -> bool:
        now = time.time()

        # ⚡ Bolt Optimization: Lazy cleanup for the specific key
        if key in self._cache:
            self._cache[key] = [t for t in self._cache[key] if now - t <= self.window]
            if not self._cache[key]:
                del self._cache[key]

        # Defer global O(N) cleanup to a periodic interval (e.g. every 60 seconds)
        monotonic_now = time.monotonic()
        if monotonic_now - getattr(self, "_last_global_cleanup", 0) > 60:
            self._cleanup(now)
            self._last_global_cleanup = monotonic_now

        if key not in self._cache:
            self._cache[key] = []

        if len(self._cache[key]) >= self.requests:
            return False

        self._cache[key].append(now)
        return True

    def _cleanup(self, now: float) -> None:
        for k in list(self._cache.keys()):
            self._cache[k] = [t for t in self._cache[k] if now - t <= self.window]
            if not self._cache[k]:
                del self._cache[k]
