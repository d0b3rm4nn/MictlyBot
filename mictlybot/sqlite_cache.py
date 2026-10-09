"""Caché de BINs en SQLite, para sobrevivir reinicios del bot.

Reemplaza la caché en memoria de :mod:`mictlybot.cache`. Guarda solo los
metadatos públicos que devuelve BinList; el TTL se aplica en lectura para no
depender de una tarea de limpieza en background.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS bins (
    bin       TEXT PRIMARY KEY,
    payload   TEXT NOT NULL,
    fetched_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bins_fetched ON bins (fetched_at);
"""


class SQLiteCache:
    def __init__(
        self,
        path: str | Path = "bins_cache.db",
        ttl_seconds: int = 86400,
    ) -> None:
        self._path = str(path)
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    @property
    def path(self) -> str:
        return self._path

    def get(self, key: str) -> Any:
        """Devuelve el payload, o ``None`` si no está o ya expiró."""
        import time

        cutoff = int(time.time()) - self._ttl
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM bins WHERE bin = ? AND fetched_at >= ?",
                (key, cutoff),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def set(self, key: str, value: Any) -> None:
        import time

        with self._lock:
            self._conn.execute(
                "INSERT INTO bins (bin, payload, fetched_at) VALUES (?, ?, ?) "
                "ON CONFLICT(bin) DO UPDATE SET payload = excluded.payload, "
                "fetched_at = excluded.fetched_at",
                (key, json.dumps(value), int(time.time())),
            )
            self._conn.commit()

    def purge_expired(self) -> int:
        """Borra entradas vencidas. Devuelve cuántas eliminó."""
        import time

        cutoff = int(time.time()) - self._ttl
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM bins WHERE fetched_at < ?", (cutoff,)
            )
            self._conn.commit()
        return cursor.rowcount

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM bins").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> SQLiteCache:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
