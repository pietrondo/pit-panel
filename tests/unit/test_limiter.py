from unittest.mock import patch

from pit_panel.web.limiter import RateLimiter


def test_ratelimiter_initialization() -> None:
    limiter = RateLimiter(requests=5, window=60)
    assert limiter.requests == 5
    assert limiter.window == 60
    assert limiter._cache == {}


def test_ratelimiter_is_allowed_happy_path() -> None:
    limiter = RateLimiter(requests=2, window=60)
    assert limiter.is_allowed("test_key") is True
    assert limiter.is_allowed("test_key") is True
    assert len(limiter._cache["test_key"]) == 2


def test_ratelimiter_is_allowed_exceeds_limit() -> None:
    limiter = RateLimiter(requests=2, window=60)
    assert limiter.is_allowed("test_key") is True
    assert limiter.is_allowed("test_key") is True
    assert limiter.is_allowed("test_key") is False
    assert len(limiter._cache["test_key"]) == 2


def test_ratelimiter_window_expiration() -> None:
    limiter = RateLimiter(requests=1, window=10)

    with patch("time.time") as mock_time:
        # T=0: First request allowed
        mock_time.return_value = 100.0
        assert limiter.is_allowed("test_key") is True

        # T=5: Second request blocked (within window)
        mock_time.return_value = 105.0
        assert limiter.is_allowed("test_key") is False

        # T=15: Third request allowed (after window)
        mock_time.return_value = 115.0
        assert limiter.is_allowed("test_key") is True


def test_ratelimiter_multi_key_isolation() -> None:
    limiter = RateLimiter(requests=1, window=60)
    assert limiter.is_allowed("key1") is True
    assert limiter.is_allowed("key2") is True
    assert limiter.is_allowed("key1") is False
    assert limiter.is_allowed("key2") is False


def test_ratelimiter_cleanup_removes_empty_keys() -> None:
    limiter = RateLimiter(requests=1, window=10)

    with patch("time.time") as mock_time:
        mock_time.return_value = 100.0
        limiter.is_allowed("key1")
        assert "key1" in limiter._cache

        # Advance time past window and trigger cleanup with another key
        mock_time.return_value = 120.0
        limiter.is_allowed("key2")

        # key1 should be removed from cache entirely
        assert "key1" not in limiter._cache
        assert "key2" in limiter._cache
