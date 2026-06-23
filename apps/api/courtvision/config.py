from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_INTERNAL_API_KEY = "local-development-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="COURTVISION_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./courtvision.db"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    internal_api_key: str = DEVELOPMENT_INTERNAL_API_KEY
    enable_delayed_live: bool = False
    stale_after_seconds: int = 120
    replay_tick_seconds: float = 0.55
    public_rate_limit_requests: int = 120
    shot_quality_rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    trust_proxy_headers: bool = False
    model_artifact_backend: Literal["local", "s3"] = "local"
    model_artifact_local_root: Path | None = None
    model_artifact_s3_bucket: str | None = Field(default=None, max_length=63)
    model_artifact_s3_prefix: str = Field(
        default="courtvision/models",
        max_length=48,
    )
    model_artifact_s3_endpoint_url: str | None = None
    model_artifact_s3_region: str | None = None
    model_artifact_max_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1,
        le=1024 * 1024 * 1024,
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        if value.startswith("postgresql://") and "+asyncpg" not in value:
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("model_artifact_s3_prefix")
    @classmethod
    def normalize_artifact_prefix(cls, value: str) -> str:
        normalized = value.strip("/")
        if not normalized or ".." in normalized.split("/"):
            raise ValueError("model_artifact_s3_prefix is invalid")
        return normalized

    @model_validator(mode="after")
    def require_production_overrides(self) -> Settings:
        if self.environment != "production":
            return self

        failures: list[str] = []
        if (
            self.internal_api_key == DEVELOPMENT_INTERNAL_API_KEY
            or len(self.internal_api_key) < 32
        ):
            failures.append(
                "COURTVISION_INTERNAL_API_KEY must be a non-default secret with at least 32 characters"
            )

        if not self.cors_origins:
            failures.append("COURTVISION_CORS_ORIGINS must include the deployed web origin")
        for origin in self.cors_origins:
            parsed_origin = urlparse(origin)
            if parsed_origin.scheme != "https":
                failures.append(
                    f"COURTVISION_CORS_ORIGINS must use https in production: {origin}"
                )
            if parsed_origin.hostname in {"localhost", "127.0.0.1", "::1"}:
                failures.append(
                    f"COURTVISION_CORS_ORIGINS cannot use loopback hosts in production: {origin}"
                )

        if not self.database_url.startswith("postgresql+asyncpg://"):
            failures.append("COURTVISION_DATABASE_URL must use PostgreSQL in production")

        redis_host = urlparse(self.redis_url).hostname
        if redis_host in {None, "localhost", "127.0.0.1", "::1"}:
            failures.append("COURTVISION_REDIS_URL must point to hosted Redis in production")

        if not self.trust_proxy_headers:
            failures.append("COURTVISION_TRUST_PROXY_HEADERS must be true in production")

        if failures:
            raise ValueError("; ".join(failures))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
