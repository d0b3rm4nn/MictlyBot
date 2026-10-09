import httpx
import pytest

from mictlybot.binlist import (
    BinError,
    BinListClient,
    BinNotFound,
    BinRateLimited,
)
from mictlybot.cache import TTLCache

PAYLOAD = {
    "bank": {"name": "BANCO DE PRUEBA"},
    "country": {"name": "Colombia", "alpha2": "CO", "emoji": "🇨🇴"},
    "scheme": "visa",
    "type": "debit",
    "brand": "VISA",
    "prepaid": True,
}


def make_client(handler, ttl=60):
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return BinListClient(
        cache=TTLCache(ttl_seconds=ttl), user_agent="test", client=client
    )


async def test_lookup_parses_payload():
    def handler(request):
        assert str(request.url).endswith("/123456")
        return httpx.Response(200, json=PAYLOAD)

    info, from_cache = await make_client(handler).lookup("123456")
    assert info.bank == "BANCO DE PRUEBA"
    assert info.emoji == "🇨🇴"
    assert info.scheme == "VISA"
    assert info.card_type == "DEBIT"
    assert info.label == "VISA VISA"
    assert info.prepaid is True
    assert from_cache is False


async def test_lookup_serves_second_call_from_cache():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=PAYLOAD)

    client = make_client(handler)
    await client.lookup("123456")
    _, from_cache = await client.lookup("123456")
    assert from_cache is True
    assert calls == 1


async def test_lookup_handles_missing_fields():
    client = make_client(lambda r: httpx.Response(200, json={"scheme": "visa"}))
    info, _ = await client.lookup("123456")
    assert info.bank == "N/A"
    assert info.country == "N/A"
    assert info.emoji == "🌐"
    assert info.card_type == "N/A"
    assert info.label == "VISA"


async def test_404_raises_not_found():
    client = make_client(lambda r: httpx.Response(404, json={}))
    with pytest.raises(BinNotFound):
        await client.lookup("000000")


async def test_429_raises_rate_limited_without_retry():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(429, json={})

    client = make_client(handler)
    with pytest.raises(BinRateLimited):
        await client.lookup("123456")
    assert calls == 1


async def test_retries_on_5xx_then_succeeds():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(500)
        return httpx.Response(200, json=PAYLOAD)

    client = make_client(handler)
    info, from_cache = await client.lookup("123456")
    assert info.bank == "BANCO DE PRUEBA"
    assert from_cache is False
    assert calls == 3


async def test_exhausted_retries_raise_binererror():
    client = make_client(lambda r: httpx.Response(503))
    with pytest.raises(BinError, match="503"):
        await client.lookup("123456")


async def test_network_error_raises_binererror():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(BinError, match="conexión"):
        await make_client(handler).lookup("123456")
