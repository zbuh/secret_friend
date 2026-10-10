import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimit:
    """In-memory sliding window: at most `limit` hits per `window` seconds for each key."""

    def __init__(self, limit: int, window: float):
        self.limit = limit
        self.window = window
        self.hits: dict[str, deque] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        if len(self.hits) > 10_000:
            self.purge(now)
        q = self.hits[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "Demasiados pedidos. Espera um pouco e tenta outra vez.")
        q.append(now)

    def purge(self, now: float) -> None:
        for key in [k for k, q in self.hits.items() if not q or q[-1] <= now - self.window]:
            del self.hits[key]

    def reset(self) -> None:
        self.hits.clear()
