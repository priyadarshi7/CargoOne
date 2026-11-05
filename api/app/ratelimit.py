"""Tiny in-memory sliding-window rate limiter for the PUBLIC (no-login) endpoints.

Limitation, by design for now: state is per API process. With several instances the effective limit is
multiplied; move to Redis / an edge rate limiter before scaling out (see docs/03-decisions.md).
"""
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_hits: int, window_s: float) -> None:
        self.max_hits, self.window_s = max_hits, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        q, cutoff = self._hits[key], time.monotonic() - self.window_s
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max_hits

    def record(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self) -> None:
        self._hits.clear()
