"""Rate limit por usuario, en memoria y con ventana deslizante simple."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_per_window: int, window_seconds: float = 60.0) -> None:
        self._max = max_per_window
        self._window = window_seconds
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> tuple[bool, float]:
        """Devuelve (permitido, segundos_para_reintentar)."""
        now = time.monotonic()
        hits = self._hits[user_id]
        while hits and now - hits[0] >= self._window:
            hits.popleft()

        if len(hits) >= self._max:
            return False, self._window - (now - hits[0])

        hits.append(now)
        return True, 0.0
