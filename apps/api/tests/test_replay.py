from __future__ import annotations

import asyncio

from courtvision.replay import ReplayCoordinator


async def test_concurrent_replay_starts_are_idempotent(database):
    coordinator = ReplayCoordinator()

    first, second = await asyncio.gather(
        coordinator.start("cv-2026-bos-nyk", tick_seconds=1),
        coordinator.start("cv-2026-bos-nyk", tick_seconds=1),
    )

    assert sorted((first[0], second[0])) == [False, True]

    running_tasks = list(coordinator._tasks.values())
    for task in running_tasks:
        task.cancel()
    await asyncio.gather(*running_tasks, return_exceptions=True)
