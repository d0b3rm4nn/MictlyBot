#!/usr/bin/env python
"""Smoke test real de bincheck.io (con cache).

Uso: python tools/smoke_bincheck.py
"""

from __future__ import annotations

import asyncio
import os

from mictlybot.bincheck import BinCheckClient, BinError
from mictlybot.config import load_config
from mictlybot.sqlite_cache import SQLiteCache

BINS = ("457173", "416916", "444353")


def _api_key(cfg) -> str | None:
    for name in ("bincheck_api_key", "api_key", "bincheck_key", "bincheck_token"):
        val = getattr(cfg, name, None)
        if val:
            return val
    return os.environ.get("BINCHECK_API_KEY")


async def main() -> None:
    cfg = load_config()
    cache = SQLiteCache(cfg.cache_db_path, cfg.cache_ttl_seconds)
    key = _api_key(cfg)
    print("api_key:", "presente" if key else "AUSENTE (revisa BINCHECK_API_KEY en .env)")
    client = BinCheckClient(cache, cfg.user_agent, api_key=key)
    try:
        for b in BINS:
            try:
                info, from_cache = await client.lookup(b)
                print(
                    f"[OK ] {b} -> bank={info.bank!r} country={info.country!r} "
                    f"scheme={info.scheme!r} cached={from_cache}"
                )
            except BinError as exc:
                print(f"[ERR] {b} -> {type(exc).__name__}: {exc}")
    finally:
        close = getattr(client, "aclose", None)
        if close:
            await close()
        cache.close()


if __name__ == "__main__":
    asyncio.run(main())
