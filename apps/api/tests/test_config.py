from __future__ import annotations

import pytest
from pydantic import ValidationError

from courtvision.config import DEVELOPMENT_INTERNAL_API_KEY, Settings


def production_settings(**overrides):
    values = {
        "environment": "production",
        "database_url": "postgresql://courtvision:secret@db.internal/courtvision",
        "redis_url": "redis://redis.internal:6379/0",
        "cors_origins": ["https://courtvision.example"],
        "internal_api_key": "x" * 32,
        "trust_proxy_headers": True,
    }
    values.update(overrides)
    return Settings(**values)


def test_production_settings_accept_hosted_defaults():
    settings = production_settings()

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url == "redis://redis.internal:6379/0"


def test_production_rejects_development_internal_key():
    with pytest.raises(ValidationError, match="non-default secret"):
        production_settings(internal_api_key=DEVELOPMENT_INTERNAL_API_KEY)


def test_production_rejects_loopback_cors_origin():
    with pytest.raises(ValidationError, match="loopback hosts"):
        production_settings(cors_origins=["http://localhost:3000"])


def test_production_requires_https_cors_origin():
    with pytest.raises(ValidationError, match="must use https"):
        production_settings(cors_origins=["http://courtvision.example"])


def test_production_rejects_sqlite_database():
    with pytest.raises(ValidationError, match="PostgreSQL"):
        production_settings(database_url="sqlite+aiosqlite:///./courtvision.db")


def test_production_rejects_loopback_redis():
    with pytest.raises(ValidationError, match="hosted Redis"):
        production_settings(redis_url="redis://127.0.0.1:6379/0")


def test_production_requires_trusted_proxy_headers():
    with pytest.raises(ValidationError, match="TRUST_PROXY_HEADERS"):
        production_settings(trust_proxy_headers=False)
