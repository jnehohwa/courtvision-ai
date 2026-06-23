from __future__ import annotations

import pytest

from courtvision.config import settings
from courtvision import e2e_server
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


def test_e2e_server_runs_worker_when_enabled(monkeypatch):
    class FakeWorkerProcess:
        def __init__(self) -> None:
            self.terminated = False
            self.killed = False

        def poll(self):
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout=None):
            return 0

        def kill(self) -> None:
            self.killed = True

    worker_process = FakeWorkerProcess()
    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return worker_process

    uvicorn_calls = []

    monkeypatch.setenv("COURTVISION_E2E_RUN_WORKER", "1")
    monkeypatch.setattr(e2e_server, "prepare_database", lambda: None)
    monkeypatch.setattr(e2e_server.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        e2e_server.uvicorn,
        "run",
        lambda *args, **kwargs: uvicorn_calls.append((args, kwargs)),
    )

    e2e_server.main()

    assert len(popen_calls) == 1
    assert popen_calls[0][0][0][-2:] == ["-m", "courtvision.worker"]
    assert popen_calls[0][1]["env"]["PYTHONUNBUFFERED"] == "1"
    assert uvicorn_calls[0][0] == ("courtvision.main:app",)
    assert worker_process.terminated
    assert not worker_process.killed
