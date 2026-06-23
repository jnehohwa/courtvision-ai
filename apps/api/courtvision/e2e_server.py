from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from courtvision.config import settings
from courtvision.seed import seed_database


def prepare_database() -> None:
    if settings.environment != "e2e":
        raise RuntimeError("The E2E server can only run in the e2e environment")

    database_url = make_url(settings.database_url)
    if database_url.get_backend_name() != "sqlite" or not database_url.database:
        raise RuntimeError("The E2E server requires an isolated SQLite database")
    database_path = Path(database_url.database)
    if database_path == Path(":memory:"):
        raise RuntimeError("The E2E server requires a file-backed SQLite database")
    expected_path = Path("/tmp/courtvision-playwright.db")
    if database_path.resolve() != expected_path.resolve():
        raise RuntimeError(
            "The E2E server only resets /tmp/courtvision-playwright.db"
        )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.unlink(missing_ok=True)

    api_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(api_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(api_root / "alembic"))
    command.upgrade(alembic_config, "head")
    asyncio.run(seed_database())


def main() -> None:
    prepare_database()
    worker_process: subprocess.Popen[str] | None = None
    if os.environ.get("COURTVISION_E2E_RUN_WORKER") == "1":
        worker_process = subprocess.Popen(
            [sys.executable, "-m", "courtvision.worker"],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
            text=True,
        )

    try:
        uvicorn.run(
            "courtvision.main:app",
            host="127.0.0.1",
            port=8000,
            log_level="warning",
        )
    finally:
        if worker_process is not None and worker_process.poll() is None:
            worker_process.terminate()
            try:
                worker_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker_process.kill()
                worker_process.wait()


if __name__ == "__main__":
    main()
