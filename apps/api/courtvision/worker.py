from __future__ import annotations

import asyncio
import json

import structlog

from courtvision.broadcast import REPLAY_QUEUE, event_bus
from courtvision.replay import replay_coordinator

logger = structlog.get_logger()


async def run_worker() -> None:
    connected = await event_bus.start(subscribe=False)
    if not connected or event_bus.redis is None:
        raise RuntimeError("Replay worker requires Redis")

    logger.info("replay_worker_ready")
    try:
        while True:
            item = await event_bus.redis.blpop(REPLAY_QUEUE, timeout=30)
            if item is None:
                continue
            _, raw_command = item
            command = json.loads(raw_command)
            game_id = str(command["game_id"])
            tick_seconds = float(command["tick_seconds"])
            try:
                event_count = await replay_coordinator.run_game(game_id, tick_seconds)
                logger.info(
                    "replay_completed",
                    game_id=game_id,
                    event_count=event_count,
                )
            finally:
                await event_bus.release_replay_lock(game_id)
    finally:
        await event_bus.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
