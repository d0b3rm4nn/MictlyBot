"""429 (cuota) y 404 (no existe) no deben colapsar en el mismo n/d."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from mictlybot import cardcheck
from mictlybot.bincheck import BinNotFound, BinRateLimited
from mictlybot.cardcheck import RATE_LIMITED, CardData, check_card, make_bin_lookup

CARD = CardData.parse("4242424242424242|12|2028|123")
TARGET = SimpleNamespace(name="fake", keys=["k"], has_key=True)


class ClienteFalso:
    def __init__(self, exc):
        self.exc = exc

    async def lookup(self, bin_number):
        raise self.exc


def test_404_mapea_a_none():
    lookup = make_bin_lookup(ClienteFalso(BinNotFound("no existe")))
    assert asyncio.run(lookup("457173")) is None


def test_429_mapea_al_centinela():
    lookup = make_bin_lookup(ClienteFalso(BinRateLimited("cuota")))
    assert asyncio.run(lookup("457173")) is RATE_LIMITED


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    async def fake_post(*args, **kwargs):
        return "Your card zip code is incorrect.", 200

    monkeypatch.setattr(cardcheck, "_post", fake_post)
    monkeypatch.setattr(cardcheck, "match_rules", lambda raw, target: ("success", "OK"))


def _correr(bin_info):
    async def lookup(_bin):
        return bin_info

    return asyncio.run(
        check_card(CARD, target=TARGET, bin_lookup=lookup, use_identity=False)
    )


def test_429_se_muestra_como_cuota():
    assert _correr(RATE_LIMITED).bank == "429 cuota"


def test_404_sigue_siendo_n_d():
    assert _correr(None).bank == ""


def test_mensaje_429_incluye_reintento():
    from mictlybot.bincheck import BinRateLimited
    from mictlybot.handlers import _mensaje_429

    con = _mensaje_429(BinRateLimited("cuota", retry_after=42))
    sin = _mensaje_429(BinRateLimited("cuota"))

    assert "cuota" in con and "42 s" in con
    assert "cuota" in sin and "reintenta" not in sin
