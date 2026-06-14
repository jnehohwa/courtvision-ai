from __future__ import annotations

import pytest

from courtvision.config import settings
from courtvision.e2e_server import prepare_database


def test_e2e_server_refuses_non_e2e_environment(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")

    with pytest.raises(RuntimeError, match="e2e environment"):
        prepare_database()


def test_e2e_server_refuses_unexpected_database_path(monkeypatch):
    monkeypatch.setattr(settings, "environment", "e2e")
    monkeypatch.setattr(
        settings,
        "database_url",
        "sqlite+aiosqlite:////tmp/unexpected-courtvision.db",
    )

    with pytest.raises(RuntimeError, match="only resets"):
        prepare_database()
