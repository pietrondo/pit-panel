import time

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


class RateLimiter:
    def __init__(self, requests: int, window: int):
        self.requests = requests
        self.window = window
        self._cache: dict[str, list[float]] = {}
        self._last_global_cleanup: float = 0.0

    def is_allowed(self, key: str) -> bool:
        now = time.time()

        # Fast path: cleanup only the requested key
        if key in self._cache:
            self._cache[key] = [t for t in self._cache[key] if now - t <= self.window]
            if not self._cache[key]:
                del self._cache[key]

        # Periodic global cleanup to prevent memory leaks from abandoned keys
        # We only do this occasionally to avoid O(N) cost on every request
        if now - self._last_global_cleanup > self.window:
            self._cleanup(now)
            self._last_global_cleanup = now

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
