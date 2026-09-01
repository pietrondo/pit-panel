import time

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


class RateLimiter:
    def __init__(self, requests: int, window: int):
        self.requests = requests
        self.window = window
        self._cache: dict[str, list[float]] = {}
        self._last_global_cleanup = time.time()
        self._global_cleanup_interval = max(60.0, float(window))

    def is_allowed(self, key: str) -> bool:
        now = time.time()

        # Defer global cleanup to periodic intervals
        if now - self._last_global_cleanup > self._global_cleanup_interval:
            self._cleanup(now)
            self._last_global_cleanup = now

        # Lazily clean only the currently accessed key
        if key in self._cache:
            self._cache[key] = [t for t in self._cache[key] if now - t <= self.window]
            if not self._cache[key]:
                del self._cache[key]

        if key not in self._cache:
            self._cache[key] = []

        if len(self._cache[key]) >= self.requests:
            return False

        self._cache[key].append(now)
        return True

    def _cleanup(self, now: float) -> None:
        for key in list(self._cache.keys()):
            self._cache[key] = [t for t in self._cache[key] if now - t <= self.window]
            if not self._cache[key]:
                del self._cache[key]
