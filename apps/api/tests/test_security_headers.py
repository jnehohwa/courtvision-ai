from __future__ import annotations

import asyncio

from courtvision.main import rate_limiter, security_headers, settings


EXPECTED_SECURITY_HEADERS = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "accelerometer=(), camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    "cross-origin-opener-policy": "same-origin",
}


def assert_security_headers(response) -> None:
    for header, expected_value in EXPECTED_SECURITY_HEADERS.items():
        assert response.headers[header] == expected_value


def test_security_headers_are_applied_to_health_and_public_api(client):
    health_response = client.get("/health")
    games_response = client.get("/api/v1/games", params={"date": "2026-06-14"})

    assert health_response.status_code == 200
    assert games_response.status_code == 200
    assert_security_headers(health_response)
    assert_security_headers(games_response)
    assert "strict-transport-security" not in health_response.headers


def test_security_headers_are_applied_to_rate_limited_responses(client):
    original_limit = rate_limiter.general_limit
    rate_limiter.general_limit = 0
    asyncio.run(rate_limiter.reset())
    try:
        response = client.get("/api/v1/games", params={"date": "2026-06-14"})
    finally:
        rate_limiter.general_limit = original_limit
        asyncio.run(rate_limiter.reset())

    assert response.status_code == 429
    assert_security_headers(response)


def test_hsts_is_limited_to_production(monkeypatch):
    assert "Strict-Transport-Security" not in security_headers()

    monkeypatch.setattr(settings, "environment", "production")

    assert (
        security_headers()["Strict-Transport-Security"]
        == "max-age=63072000; includeSubDomains; preload"
    )
