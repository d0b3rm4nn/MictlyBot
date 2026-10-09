"""Caché TTL en memoria. Alternativa ligera a la caché SQLite persistente."""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    """Guarda valores en memoria con caducidad. No persiste reinicios."""

    def __init__(self, ttl_seconds: int, max_entries: int = 1024) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._data: dict[str, tuple[float, Any]] = {}

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    def get(self, key: str) -> Any:
        """Devuelve el valor, o ``None`` si no está o expiró."""
        entry = self._data.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at <= time.monotonic():
            del self._data[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._data) >= self._max:
            oldest = min(self._data, key=lambda k: self._data[k][0])
            del self._data[oldest]
        self._data[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)
