"""_lookup_bin distingue el motivo del fallo en vez de aplastar a N/A."""

import asyncio

from mictlybot.bincheck import BinError, BinNotFound, BinRateLimited
from mictlybot.handlers import _lookup_bin


class _Client:
    def __init__(self, exc):
        self._exc = exc

    async def lookup(self, _bin):
        raise self._exc


class _Ctx:
    def __init__(self, exc):
        self.bot_data = {"bin_client": _Client(exc)}


def _run(exc):
    return asyncio.run(_lookup_bin(_Ctx(exc), "416916"))


def test_429_con_retry_after():
    assert _run(BinRateLimited("x", retry_after=42)) == ("n/d [429/42s]", "n/d [429/42s]")


def test_429_sin_retry_after():
    assert _run(BinRateLimited("x")) == ("n/d [429]", "n/d [429]")


def test_404():
    assert _run(BinNotFound("x")) == ("n/d [404]", "n/d [404]")


def test_error_generico():
    assert _run(BinError("x")) == ("n/d [err]", "n/d [err]")
