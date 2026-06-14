from __future__ import annotations

import asyncio
import json
from collections import defaultdict

from fastapi import WebSocket
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from courtvision.config import settings
from courtvision.schemas import WebSocketEnvelope

EVENT_CHANNEL = "courtvision:events"
REPLAY_QUEUE = "courtvision:replay:commands"
REPLAY_LOCK_PREFIX = "courtvision:replay:lock:"


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, game_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[game_id].add(websocket)

    async def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[game_id].discard(websocket)

    async def broadcast(self, envelope: WebSocketEnvelope) -> None:
        stale_connections: list[WebSocket] = []
        for connection in tuple(self._connections[envelope.game_id]):
            try:
                await connection.send_json(envelope.model_dump(mode="json"))
            except Exception:
                stale_connections.append(connection)

        if stale_connections:
            async with self._lock:
                for connection in stale_connections:
                    self._connections[envelope.game_id].discard(connection)


connection_manager = ConnectionManager()


class EventBus:
    def __init__(self) -> None:
        self.redis: Redis | None = None
        self._pubsub: PubSub | None = None
        self._listener: asyncio.Task[None] | None = None

    async def start(self, *, subscribe: bool) -> bool:
        redis = Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.5,
            socket_timeout=1,
            decode_responses=True,
        )
        try:
            await redis.ping()
        except Exception:
            await redis.aclose()
            return False

        self.redis = redis
        if subscribe:
            self._pubsub = redis.pubsub()
            await self._pubsub.subscribe(EVENT_CHANNEL)
            self._listener = asyncio.create_task(self._listen())
        return True

    async def stop(self) -> None:
        if self._listener:
            self._listener.cancel()
            await asyncio.gather(self._listener, return_exceptions=True)
            self._listener = None
        if self._pubsub:
            await self._pubsub.aclose()
            self._pubsub = None
        if self.redis:
            await self.redis.aclose()
            self.redis = None

    async def publish(self, envelope: WebSocketEnvelope) -> None:
        if self.redis:
            try:
                await self.redis.publish(
                    EVENT_CHANNEL,
                    envelope.model_dump_json(),
                )
                return
            except Exception:
                await self.stop()
        await connection_manager.broadcast(envelope)

    async def enqueue_replay(self, game_id: str, tick_seconds: float) -> bool:
        if not self.redis:
            return False

        lock_key = f"{REPLAY_LOCK_PREFIX}{game_id}"
        acquired = await self.redis.set(lock_key, "queued", ex=300, nx=True)
        if not acquired:
            return False
        try:
            await self.redis.rpush(
                REPLAY_QUEUE,
                json.dumps({"game_id": game_id, "tick_seconds": tick_seconds}),
            )
        except Exception:
            await self.redis.delete(lock_key)
            raise
        return True

    async def release_replay_lock(self, game_id: str) -> None:
        if self.redis:
            await self.redis.delete(f"{REPLAY_LOCK_PREFIX}{game_id}")

    async def _listen(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                envelope = WebSocketEnvelope.model_validate_json(message["data"])
                await connection_manager.broadcast(envelope)
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._pubsub:
                await self._pubsub.aclose()
                self._pubsub = None
            if self.redis:
                await self.redis.aclose()
                self.redis = None


event_bus = EventBus()
