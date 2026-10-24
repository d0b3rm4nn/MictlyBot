"""Pruebas del parseo de BinCheck (sin red)."""

from __future__ import annotations

import asyncio

import pytest

from mictlybot.bincheck import (
    NOT_FOUND_MARK,
    BinCheckClient,
    BinNotFound,
    _parse,
    flag_emoji,
    pretty_country,
)


class _Cache:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}

    def get(self, key: str) -> object:
        return self.data.get(key)

    def set(self, key: str, value: object) -> None:
        self.data[key] = value


def test_flag_emoji():
    assert flag_emoji("MX") == "🇲🇽"
    assert flag_emoji("us") == "🇺🇸"
    assert flag_emoji("") == "🌐"
    assert flag_emoji("XXX") == "🌐"


def test_pretty_country():
    assert pretty_country("MEXICO") == "Mexico"
    assert pretty_country("UNITED STATES") == "United States"
    assert pretty_country("N/A") == "N/A"


def test_parse_lee_el_sobre_bin():
    payload = {
        "success": True,
        "code": 200,
        "BIN": {
            "bin": "444353",
            "brand": "VISA",
            "type": "CREDIT",
            "level": "CLASSIC",
            "issuer": {"name": "Bancoppel S.A."},
            "country": {"name": "MEXICO", "alpha2": "MX", "currency": "MXN"},
            "prepaid": False,
        },
    }
    info = _parse("444353", payload)
    assert info.bank == "Bancoppel S.A."
    assert info.country == "Mexico"
    assert info.country_code == "MX"
    assert info.emoji == "🇲🇽"
    assert info.scheme == "VISA"
    assert info.card_type == "CREDIT"
    assert info.brand == "CLASSIC"
    assert info.prepaid is False
    assert info.label == "VISA CLASSIC"


def test_parse_tolera_payload_sin_sobre():
    info = _parse(
        "444353",
        {"brand": "VISA", "issuer": {"name": "X"}, "country": {"alpha2": "US"}},
    )
    assert info.bank == "X"
    assert info.country_code == "US"
    assert info.emoji == "🇺🇸"


def test_parse_tolera_formato_viejo_de_binlist():
    info = _parse(
        "444353",
        {"bank": {"name": "BANCO VIEJO"}, "country": {"alpha2": "MX"}, "scheme": "VISA"},
    )
    assert info.bank == "BANCO VIEJO"
    assert info.scheme == "VISA"
    assert info.emoji == "🇲🇽"


def test_404_se_cachea_y_no_repega():
    cache = _Cache()
    client = BinCheckClient(cache, "ua", api_key="k")
    llamadas: list[str] = []

    async def fake_fetch(bin_number: str):
        llamadas.append(bin_number)
        raise BinNotFound("no existe")

    client._fetch = fake_fetch  # type: ignore[method-assign]

    async def run() -> None:
        for _ in range(2):
            with pytest.raises(BinNotFound):
                await client.lookup("999999")

    asyncio.run(run())
    assert llamadas == ["999999"]  # la segunda salio de la cache
    assert cache.data["999999"] == {NOT_FOUND_MARK: True}


def test_formato_binlist_mapea_brand_como_submarca():
    info = _parse(
        "457173",
        {
            "bank": {"name": "X"},
            "country": {"alpha2": "DK"},
            "scheme": "VISA",
            "brand": "Visa/Dankort",
            "type": "Debit",
        },
    )
    assert info.scheme == "VISA"
    assert info.brand == "Visa/Dankort"
    assert info.card_type == "DEBIT"
    assert info.label == "VISA Visa/Dankort"
