import time

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


class RateLimiter:
    def __init__(self, requests: int, window: int):
        self.requests = requests
        self.window = window
        self._cache: dict[str, list[float]] = {}
        self._last_cleanup = time.time()

    def is_allowed(self, key: str) -> bool:
        now = time.time()

        # Periodic global cleanup to prevent memory leak from inactive keys
        if now - self._last_cleanup > self.window:
            self._cleanup_all(now)

        lst = self._cache.get(key)
        if lst is None:
            lst = []
            self._cache[key] = lst
        else:
            # Clean only the current key to avoid O(N) over all keys on every request
            cutoff = now - self.window
            idx = 0
            for i, t in enumerate(lst):
                if t > cutoff:
                    idx = i
                    break
            else:
                idx = len(lst)
            if idx > 0:
                del lst[:idx]

        if len(lst) >= self.requests:
            return False

        lst.append(now)
        return True

    def _cleanup_all(self, now: float) -> None:
        cutoff = now - self.window
        for k in list(self._cache.keys()):
            lst = self._cache[k]
            idx = 0
            for i, t in enumerate(lst):
                if t > cutoff:
                    idx = i
                    break
            else:
                idx = len(lst)
            if idx == len(lst):
                del self._cache[k]
            elif idx > 0:
                del lst[:idx]
        self._last_cleanup = now
