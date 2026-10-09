import time

from mictlybot.cache import TTLCache


def test_set_and_get():
    cache = TTLCache(ttl_seconds=60)
    cache.set("123456", {"bank": "Test"})
    assert cache.get("123456") == {"bank": "Test"}


def test_miss_returns_none():
    assert TTLCache(ttl_seconds=60).get("nope") is None


def test_expired_entry_is_evicted():
    cache = TTLCache(ttl_seconds=1)
    cache.set("123456", 1)
    time.sleep(1.1)
    assert cache.get("123456") is None


def test_evicts_oldest_when_full():
    cache = TTLCache(ttl_seconds=60, max_entries=2)
    cache.set("a", 1)
    time.sleep(0.01)
    cache.set("b", 2)
    time.sleep(0.01)
    cache.set("c", 3)
    assert len(cache) == 2
    assert cache.get("a") is None
