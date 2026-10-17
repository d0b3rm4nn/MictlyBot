"""Lectura de proxy.txt con rotación aleatoria y recarga en caliente."""

from __future__ import annotations

import random
import threading
from pathlib import Path

from .config import resolve_path


def normalize(raw: str) -> str:
    """host:port | host:port:user:pass | socks5://... -> URL usable."""
    raw = raw.strip()
    if "://" in raw:
        return raw
    parts = raw.split(":")
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}"
    if len(parts) == 4:
        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    return f"http://{raw}"


class ProxyPool:
    """Un proxy al azar por petición. Recarga el archivo si cambia."""

    def __init__(self, path: str, enabled: bool = True) -> None:
        self._path: Path = resolve_path(path)
        self._enabled = enabled
        self._lock = threading.Lock()
        self._mtime = 0.0
        self._proxies: tuple[str, ...] = ()

    def load(self) -> tuple[str, ...]:
        if not self._enabled or not self._path.exists():
            return ()
        mtime = self._path.stat().st_mtime
        with self._lock:
            if mtime == self._mtime:
                return self._proxies
            lines = [
                normalize(line)
                for line in self._path.read_text(
                    encoding="utf-8", errors="ignore"
                ).splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]
            self._mtime = mtime
            self._proxies = tuple(lines)
            return self._proxies

    def random(self) -> str | None:
        proxies = self.load()
        return random.choice(proxies) if proxies else None

    def count(self) -> int:
        return len(self.load())

    @property
    def enabled(self) -> bool:
        return self._enabled
