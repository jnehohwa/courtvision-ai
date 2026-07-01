from __future__ import annotations

import asyncio
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TextIO

import uvicorn
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy.engine import make_url

from courtvision.config import settings
from courtvision.seed import seed_database

WORKER_READY_MARKER = "replay_worker_ready"
WORKER_READY_TIMEOUT_SECONDS = 10


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


async def _reset_redis_database() -> None:
    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.flushdb()
    finally:
        await redis.aclose()


def reset_redis_database() -> None:
    if settings.environment != "e2e":
        raise RuntimeError("The E2E Redis reset can only run in the e2e environment")
    asyncio.run(_reset_redis_database())
    print("courtvision_e2e_redis_reset", flush=True)


def _drain_worker_output(
    stream: TextIO,
    output_queue: "queue.Queue[str]",
) -> None:
    for line in stream:
        print(line, end="", flush=True)
        output_queue.put(line)


def start_worker_process() -> subprocess.Popen[str]:
    worker_process = subprocess.Popen(
        [sys.executable, "-m", "courtvision.worker"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if worker_process.stdout is None:
        worker_process.terminate()
        raise RuntimeError("Replay worker stdout was not captured")

    output_queue: queue.Queue[str] = queue.Queue()
    threading.Thread(
        target=_drain_worker_output,
        args=(worker_process.stdout, output_queue),
        daemon=True,
    ).start()

    deadline = time.monotonic() + WORKER_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if worker_process.poll() is not None:
            raise RuntimeError("Replay worker exited before becoming ready")
        try:
            line = output_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if WORKER_READY_MARKER in line:
            print("courtvision_e2e_worker_ready", flush=True)
            return worker_process

    worker_process.terminate()
    try:
        worker_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        worker_process.kill()
        worker_process.wait()
    raise RuntimeError("Replay worker did not become ready before timeout")


def watch_worker_process(worker_process: subprocess.Popen[str]) -> None:
    return_code = worker_process.wait()
    print(
        f"courtvision_e2e_worker_exited return_code={return_code}",
        flush=True,
    )


def main() -> None:
    prepare_database()
    worker_process: subprocess.Popen[str] | None = None
    if os.environ.get("COURTVISION_E2E_RUN_WORKER") == "1":
        print("courtvision_e2e_worker_starting", flush=True)
        reset_redis_database()
        worker_process = start_worker_process()
        threading.Thread(
            target=watch_worker_process,
            args=(worker_process,),
            daemon=True,
        ).start()

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
