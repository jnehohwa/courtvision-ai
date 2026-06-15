from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from courtvision.broadcast import (
    ACKNOWLEDGE_REPLAY_SCRIPT,
    EVENT_CHANNEL,
    REPLAY_LOCK_PREFIX,
    REPLAY_PROCESSING_QUEUE,
    REPLAY_QUEUE,
)
from courtvision.schemas import WebSocketEnvelope

pytestmark = pytest.mark.skipif(
    os.environ.get("COURTVISION_REDIS_INTEGRATION") != "1",
    reason="requires the dedicated Redis integration job",
)

GAME_ID = "cv-2026-bos-nyk"
API_ROOT = Path(__file__).resolve().parents[1]


async def next_envelope(pubsub: PubSub, timeout: float = 10) -> WebSocketEnvelope:
    async with asyncio.timeout(timeout):
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=1,
            )
            if message is not None:
                return WebSocketEnvelope.model_validate_json(message["data"])
            await asyncio.sleep(0.01)


async def start_worker() -> asyncio.subprocess.Process:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "courtvision.worker",
        cwd=API_ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    async with asyncio.timeout(10):
        while True:
            line = await process.stdout.readline()
            if not line:
                raise AssertionError("Replay worker exited before becoming ready")
            if b"replay_worker_ready" in line:
                return process


async def stop_worker(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        process.kill()
        await process.wait()


async def test_worker_restart_recovers_claimed_replay(client):
    redis = Redis.from_url(
        os.environ.get("COURTVISION_REDIS_URL", "redis://127.0.0.1:6379/0"),
        decode_responses=True,
    )
    pubsub = redis.pubsub()
    first_worker: asyncio.subprocess.Process | None = None
    second_worker: asyncio.subprocess.Process | None = None

    try:
        await redis.delete(
            REPLAY_QUEUE,
            REPLAY_PROCESSING_QUEUE,
            f"{REPLAY_LOCK_PREFIX}{GAME_ID}",
        )
        await pubsub.subscribe(EVENT_CHANNEL)
        await pubsub.get_message(timeout=1)

        first_worker = await start_worker()
        response = client.post(
            f"/internal/replays/{GAME_ID}/start",
            headers={"X-Internal-Key": "local-development-key"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "started"

        first_sequences: list[int] = []
        while max(first_sequences, default=0) < 5:
            envelope = await next_envelope(pubsub)
            if envelope.type == "play_added":
                first_sequences.append(envelope.sequence)

        await stop_worker(first_worker)
        first_worker = None
        assert await redis.llen(REPLAY_PROCESSING_QUEUE) == 1
        assert await redis.exists(f"{REPLAY_LOCK_PREFIX}{GAME_ID}") == 1

        second_worker = await start_worker()
        restarted = False
        recovered_sequences: list[int] = []
        while True:
            envelope = await next_envelope(pubsub)
            if (
                envelope.type == "source_status"
                and envelope.payload.get("status") == "replay_started"
            ):
                restarted = True
                recovered_sequences.clear()
                continue
            if restarted and envelope.type == "play_added":
                recovered_sequences.append(envelope.sequence)
            if restarted and envelope.type == "replay_completed":
                break

        assert recovered_sequences == list(range(1, 21))
        async with asyncio.timeout(5):
            while await redis.llen(REPLAY_PROCESSING_QUEUE) != 0:
                await asyncio.sleep(0.01)
        assert await redis.exists(f"{REPLAY_LOCK_PREFIX}{GAME_ID}") == 0
    finally:
        if first_worker is not None:
            await stop_worker(first_worker)
        if second_worker is not None:
            await stop_worker(second_worker)
        await pubsub.aclose()
        await redis.aclose()


async def test_acknowledgement_preserves_a_newer_lock_owner():
    redis = Redis.from_url(
        os.environ.get("COURTVISION_REDIS_URL", "redis://127.0.0.1:6379/0"),
        decode_responses=True,
    )
    raw_command = '{"game_id":"game-1","lock_token":"old"}'
    lock_key = f"{REPLAY_LOCK_PREFIX}game-1"

    try:
        await redis.delete(REPLAY_PROCESSING_QUEUE, lock_key)
        await redis.rpush(REPLAY_PROCESSING_QUEUE, raw_command)
        await redis.set(lock_key, "new-owner")
        await redis.eval(
            ACKNOWLEDGE_REPLAY_SCRIPT,
            2,
            REPLAY_PROCESSING_QUEUE,
            lock_key,
            raw_command,
            "old-owner",
        )

        assert await redis.llen(REPLAY_PROCESSING_QUEUE) == 0
        assert await redis.get(lock_key) == "new-owner"
    finally:
        await redis.delete(REPLAY_PROCESSING_QUEUE, lock_key)
        await redis.aclose()


async def test_worker_discards_malformed_pending_command():
    redis = Redis.from_url(
        os.environ.get("COURTVISION_REDIS_URL", "redis://127.0.0.1:6379/0"),
        decode_responses=True,
    )
    worker: asyncio.subprocess.Process | None = None

    try:
        await redis.delete(REPLAY_QUEUE, REPLAY_PROCESSING_QUEUE)
        await redis.rpush(REPLAY_PROCESSING_QUEUE, "not-json")
        worker = await start_worker()

        async with asyncio.timeout(5):
            while await redis.llen(REPLAY_PROCESSING_QUEUE) != 0:
                await asyncio.sleep(0.01)
        assert worker.returncode is None
    finally:
        if worker is not None:
            await stop_worker(worker)
        await redis.delete(REPLAY_QUEUE, REPLAY_PROCESSING_QUEUE)
        await redis.aclose()
