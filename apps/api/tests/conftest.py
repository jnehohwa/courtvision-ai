from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TEST_DATABASE = Path(__file__).parent / "test-courtvision.db"
os.environ["COURTVISION_DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DATABASE}"
os.environ["COURTVISION_REPLAY_TICK_SECONDS"] = (
    "0.05" if os.environ.get("COURTVISION_REDIS_INTEGRATION") == "1" else "0.001"
)

from courtvision.main import app  # noqa: E402
from courtvision.database import create_schema  # noqa: E402
from courtvision.seed import seed_database  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def database():
    if TEST_DATABASE.exists():
        TEST_DATABASE.unlink()
    import asyncio

    asyncio.run(create_schema())
    asyncio.run(seed_database())
    yield
    if TEST_DATABASE.exists():
        TEST_DATABASE.unlink()


@pytest.fixture
def client(database):
    with TestClient(app) as test_client:
        yield test_client
