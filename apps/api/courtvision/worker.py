from __future__ import annotations

import asyncio

import structlog
from pydantic import BaseModel, Field, ValidationError

from courtvision.broadcast import (
    REPLAY_PROCESSING_QUEUE,
    REPLAY_QUEUE,
    event_bus,
)
from courtvision.replay import replay_coordinator

logger = structlog.get_logger()


class ReplayCommand(BaseModel):
    game_id: str = Field(min_length=1, max_length=128)
    tick_seconds: float = Field(gt=0, le=10)
    lock_token: str = Field(min_length=32, max_length=64)


async def next_replay_command() -> str | None:
    assert event_bus.redis is not None

    # Render runs one replay worker. A pending item is therefore an interrupted
    # command owned by the previous process and must be recovered before new work.
    pending = await event_bus.redis.lindex(REPLAY_PROCESSING_QUEUE, -1)
    if pending is not None:
        return pending
    return await event_bus.redis.blmove(
        REPLAY_QUEUE,
        REPLAY_PROCESSING_QUEUE,
        timeout=30,
        src="RIGHT",
        dest="LEFT",
    )


async def process_replay_command(raw_command: str) -> None:
    try:
        command = ReplayCommand.model_validate_json(raw_command)
    except ValidationError:
        logger.exception("invalid_replay_command", raw_command=raw_command)
        await event_bus.discard_replay(raw_command)
        return

    try:
        event_count = await replay_coordinator.run_game(
            command.game_id,
            command.tick_seconds,
        )
        logger.info(
            "replay_completed",
            game_id=command.game_id,
            event_count=event_count,
        )
    except Exception:
        logger.exception("replay_failed", game_id=command.game_id)
        raise
    else:
        await event_bus.acknowledge_replay(
            raw_command,
            command.game_id,
            command.lock_token,
        )


async def run_worker() -> None:
    connected = await event_bus.start(subscribe=False)
    if not connected or event_bus.redis is None:
        raise RuntimeError("Replay worker requires Redis")

    logger.info("replay_worker_ready")
    try:
        while True:
            raw_command = await next_replay_command()
            if raw_command is None:
                continue
            await process_replay_command(raw_command)
    finally:
        await event_bus.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
