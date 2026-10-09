import time

import pytest

from mictlybot.ratelimit import RateLimiter


def test_allows_up_to_limit():
    limiter = RateLimiter(max_per_window=3, window_seconds=60)
    for _ in range(3):
        allowed, _ = limiter.allow(1)
        assert allowed


def test_blocks_after_limit_and_reports_wait():
    limiter = RateLimiter(max_per_window=2, window_seconds=60)
    limiter.allow(1)
    limiter.allow(1)
    allowed, retry_after = limiter.allow(1)
    assert not allowed
    assert 0 < retry_after <= 60


def test_limits_are_per_user():
    limiter = RateLimiter(max_per_window=1, window_seconds=60)
    assert limiter.allow(1)[0]
    assert limiter.allow(2)[0]


def test_window_slides():
    limiter = RateLimiter(max_per_window=1, window_seconds=0.2)
    assert limiter.allow(1)[0]
    assert not limiter.allow(1)[0]
    time.sleep(0.25)
    assert limiter.allow(1)[0]


def test_default_window_is_sixty_seconds():
    limiter = RateLimiter(max_per_window=1)
    limiter.allow(1)
    _, retry_after = limiter.allow(1)
    assert 55 < retry_after <= 60


@pytest.mark.parametrize("user_id", [0, -1, 999999])
def test_arbitrary_ids(user_id):
    assert RateLimiter(max_per_window=5).allow(user_id)[0]
