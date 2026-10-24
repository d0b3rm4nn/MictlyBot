import json
import time

import pytest

from mictlybot.bincheck import BinInfo
from mictlybot.sqlite_cache import SQLiteCache

INFO = {
    "bin_number": "123456",
    "bank": "BANCO",
    "country": "Colombia",
    "country_code": "CO",
    "emoji": "CO",
    "scheme": "VISA",
    "card_type": "DEBIT",
    "brand": "VISA",
    "prepaid": False,
}


@pytest.fixture
def cache(tmp_path):
    with SQLiteCache(tmp_path / "t.db", ttl_seconds=60) as c:
        yield c


def test_set_and_get_roundtrips(cache):
    cache.set("123456", INFO)
    assert cache.get("123456") == INFO


def test_miss_returns_none(cache):
    assert cache.get("999999") is None


def test_expired_entry_is_treated_as_miss(cache):
    c = SQLiteCache(cache.path, ttl_seconds=1)
    c.set("123456", INFO)
    # fetched_at es un entero de segundos; hay que pasar el segundo completo.
    time.sleep(2.1)
    assert c.get("123456") is None
    c.close()


def test_upsert_overwrites_existing_key(cache):
    cache.set("123456", INFO)
    updated = {**INFO, "bank": "OTRO"}
    cache.set("123456", updated)
    assert cache.get("123456")["bank"] == "OTRO"
    assert cache.count() == 1


def test_purge_expired_removes_only_stale(cache):
    cache.set("fresh", INFO)
    with cache._conn:
        cache._conn.execute(
            "UPDATE bins SET fetched_at = ? WHERE bin = ?",
            (int(time.time()) - 10_000, "fresh"),
        )
    removed = cache.purge_expired()
    assert removed == 1
    assert cache.get("fresh") is None


def test_purge_keeps_unexpired(cache):
    cache.set("fresh", INFO)
    assert cache.purge_expired() == 0
    assert cache.count() == 1


def test_survives_reopen(tmp_path):
    path = tmp_path / "persist.db"
    first = SQLiteCache(path, ttl_seconds=600)
    first.set("123456", INFO)
    first.close()

    second = SQLiteCache(path, ttl_seconds=600)
    assert second.get("123456") == INFO
    second.close()


def test_stores_serializable_json_not_object(cache):
    cache.set("123456", INFO)
    raw = cache._conn.execute("SELECT payload FROM bins").fetchone()[0]
    assert json.loads(raw) == INFO


def test_works_with_bininfo_dataclass(cache):
    info = BinInfo(**INFO)
    cache.set("123456", info.as_dict())
    assert BinInfo.from_dict(cache.get("123456")) == info


def test_count_tracks_entries(cache):
    assert cache.count() == 0
    cache.set("a", INFO)
    cache.set("b", INFO)
    assert cache.count() == 2


def test_ttl_property_exposed(cache):
    assert cache.ttl_seconds == 60


def test_creates_missing_tables(tmp_path):
    path = tmp_path / "new.db"
    c = SQLiteCache(path, ttl_seconds=60)
    tables = {
        r[0]
        for r in c._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "bins" in tables
    c.close()
