from __future__ import annotations

import asyncio

from courtvision.main import rate_limiter
from courtvision.rate_limit import RateLimiter


async def test_in_memory_rate_limiter_resets_by_window():
    now = 120.0
    limiter = RateLimiter(
        general_limit=2,
        shot_quality_limit=1,
        window_seconds=60,
        clock=lambda: now,
    )

    first = await limiter.check(
        client_identifier="client-1",
        bucket_name="public-read",
    )
    second = await limiter.check(
        client_identifier="client-1",
        bucket_name="public-read",
    )
    blocked = await limiter.check(
        client_identifier="client-1",
        bucket_name="public-read",
    )

    assert first.allowed and first.remaining == 1
    assert second.allowed and second.remaining == 0
    assert not blocked.allowed
    assert blocked.retry_after_seconds == 60
    assert blocked.reset_epoch_seconds == 180

    now = 180.0
    reset = await limiter.check(
        client_identifier="client-1",
        bucket_name="public-read",
    )
    assert reset.allowed and reset.remaining == 1


async def test_shot_quality_has_a_separate_limit_bucket():
    limiter = RateLimiter(
        general_limit=5,
        shot_quality_limit=1,
        window_seconds=60,
        clock=lambda: 120.0,
    )

    public_read = await limiter.check(
        client_identifier="client-1",
        bucket_name="public-read",
    )
    shot = await limiter.check(
        client_identifier="client-1",
        bucket_name="shot-quality",
    )
    blocked_shot = await limiter.check(
        client_identifier="client-1",
        bucket_name="shot-quality",
    )

    assert public_read.allowed
    assert shot.allowed
    assert not blocked_shot.allowed


def test_public_api_returns_rate_limit_headers_and_429(client):
    original_limit = rate_limiter.general_limit
    rate_limiter.general_limit = 2
    asyncio.run(rate_limiter.reset())
    try:
        first = client.get(
            "/api/v1/games",
            params={"date": "2026-06-14"},
        )
        second = client.get(
            "/api/v1/games",
            params={"date": "2026-06-14"},
        )
        blocked = client.get(
            "/api/v1/games",
            params={"date": "2026-06-14"},
        )
    finally:
        rate_limiter.general_limit = original_limit
        asyncio.run(rate_limiter.reset())

    assert first.status_code == 200
    assert first.headers["x-ratelimit-limit"] == "2"
    assert first.headers["x-ratelimit-reset"].isdigit()
    assert second.headers["x-ratelimit-remaining"] == "0"
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Rate limit exceeded"}
    assert int(blocked.headers["retry-after"]) >= 1


def test_cors_exposes_rate_limit_headers_to_browser_clients(client):
    response = client.get(
        "/api/v1/games",
        params={"date": "2026-06-14"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    exposed_headers = {
        header.strip().lower()
        for header in response.headers["access-control-expose-headers"].split(",")
    }
    assert {
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "retry-after",
    }.issubset(exposed_headers)
