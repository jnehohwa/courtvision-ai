from __future__ import annotations

import hashlib
import time
from threading import Lock
from collections.abc import Callable
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    def __init__(
        self,
        *,
        general_limit: int,
        shot_quality_limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.general_limit = general_limit
        self.shot_quality_limit = shot_quality_limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._memory_counts: dict[tuple[str, str, int], int] = {}
        self._memory_lock = Lock()

    async def check(
        self,
        *,
        client_identifier: str,
        bucket_name: str,
        redis: Redis | None = None,
    ) -> RateLimitDecision:
        now = self.clock()
        window = int(now // self.window_seconds)
        retry_after = max(1, int(self.window_seconds - (now % self.window_seconds)))
        limit = (
            self.shot_quality_limit
            if bucket_name == "shot-quality"
            else self.general_limit
        )
        client_hash = hashlib.sha256(client_identifier.encode()).hexdigest()[:20]

        count: int | None = None
        if redis is not None:
            key = f"courtvision:rate:{bucket_name}:{window}:{client_hash}"
            try:
                count = int(await redis.incr(key))
                if count == 1:
                    await redis.expire(key, self.window_seconds + 1)
            except Exception:
                count = None

        if count is None:
            count = await self._increment_memory(
                client_hash=client_hash,
                bucket_name=bucket_name,
                window=window,
            )

        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=max(limit - count, 0),
            retry_after_seconds=retry_after,
        )

    async def reset(self) -> None:
        with self._memory_lock:
            self._memory_counts.clear()

    async def _increment_memory(
        self,
        *,
        client_hash: str,
        bucket_name: str,
        window: int,
    ) -> int:
        key = (client_hash, bucket_name, window)
        with self._memory_lock:
            self._memory_counts = {
                candidate: count
                for candidate, count in self._memory_counts.items()
                if candidate[2] >= window - 1
            }
            count = self._memory_counts.get(key, 0) + 1
            self._memory_counts[key] = count
            return count
