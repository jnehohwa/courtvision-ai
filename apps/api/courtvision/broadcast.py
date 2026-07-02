from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from uuid import uuid4

import structlog
from fastapi import WebSocket
from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from courtvision.config import settings
from courtvision.schemas import WebSocketEnvelope

EVENT_CHANNEL = "courtvision:events"
REPLAY_QUEUE = "courtvision:replay:commands"
REPLAY_PROCESSING_QUEUE = "courtvision:replay:processing"
REPLAY_LOCK_PREFIX = "courtvision:replay:lock:"
ACKNOWLEDGE_REPLAY_SCRIPT = """
local removed = redis.call("LREM", KEYS[1], 1, ARGV[1])
if redis.call("GET", KEYS[2]) == ARGV[2] then
    redis.call("DEL", KEYS[2])
end
return removed
"""
logger = structlog.get_logger()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._last_sequences: dict[WebSocket, int] = {}
        self._lock = asyncio.Lock()

    async def connect(self, game_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[game_id].add(websocket)
            self._last_sequences[websocket] = 0

    async def disconnect(self, game_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[game_id].discard(websocket)
            self._last_sequences.pop(websocket, None)

    async def broadcast(self, envelope: WebSocketEnvelope) -> None:
        stale_connections: list[WebSocket] = []
        connections = tuple(self._connections[envelope.game_id])
        for connection in connections:
            try:
                await connection.send_json(envelope.model_dump(mode="json"))
                await self.note_sequence(connection, envelope.sequence)
            except Exception:
                stale_connections.append(connection)

        if stale_connections:
            async with self._lock:
                for connection in stale_connections:
                    self._connections[envelope.game_id].discard(connection)
                    self._last_sequences.pop(connection, None)

    async def count(self, game_id: str) -> int:
        async with self._lock:
            return len(self._connections[game_id])

    async def note_sequence(self, websocket: WebSocket, sequence: int) -> None:
        async with self._lock:
            if websocket not in self._last_sequences:
                return
            self._last_sequences[websocket] = max(
                self._last_sequences[websocket],
                sequence,
            )

    async def last_sequence(self, websocket: WebSocket, default: int = 0) -> int:
        async with self._lock:
            return self._last_sequences.get(websocket, default)


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
            socket_timeout=None,
            decode_responses=True,
        )
        try:
            await redis.ping()
        except Exception:
            await redis.aclose()
            logger.warning("event_bus_unavailable", redis_url=settings.redis_url)
            return False

        self.redis = redis
        logger.info("event_bus_connected", subscribe=subscribe)
        if subscribe:
            self._pubsub = redis.pubsub()
            await self._pubsub.subscribe(EVENT_CHANNEL)
            self._listener = asyncio.create_task(self._listen())
            logger.info("event_bus_subscribed", channel=EVENT_CHANNEL)
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
                logger.info(
                    "event_bus_published",
                    event_type=envelope.type,
                    game_id=envelope.game_id,
                    sequence=envelope.sequence,
                )
                return
            except Exception:
                logger.exception(
                    "event_bus_publish_failed",
                    event_type=envelope.type,
                    game_id=envelope.game_id,
                    sequence=envelope.sequence,
                )
                await self.stop()
        await connection_manager.broadcast(envelope)

    async def enqueue_replay(self, game_id: str, tick_seconds: float) -> bool:
        if not self.redis:
            return False

        lock_key = f"{REPLAY_LOCK_PREFIX}{game_id}"
        lock_token = uuid4().hex
        acquired = await self.redis.set(lock_key, lock_token, ex=300, nx=True)
        if not acquired:
            return False
        raw_command = json.dumps(
            {
                "game_id": game_id,
                "tick_seconds": tick_seconds,
                "lock_token": lock_token,
            }
        )
        try:
            await self.redis.rpush(REPLAY_QUEUE, raw_command)
        except Exception:
            await self._delete_lock_if_owned(lock_key, lock_token)
            raise
        logger.info("replay_enqueued", game_id=game_id, tick_seconds=tick_seconds)
        return True

    async def acknowledge_replay(
        self,
        raw_command: str,
        game_id: str,
        lock_token: str,
    ) -> None:
        if self.redis:
            await self.redis.eval(
                ACKNOWLEDGE_REPLAY_SCRIPT,
                2,
                REPLAY_PROCESSING_QUEUE,
                f"{REPLAY_LOCK_PREFIX}{game_id}",
                raw_command,
                lock_token,
            )

    async def discard_replay(self, raw_command: str) -> None:
        if self.redis:
            await self.redis.lrem(REPLAY_PROCESSING_QUEUE, 1, raw_command)

    async def _delete_lock_if_owned(self, lock_key: str, lock_token: str) -> None:
        if self.redis:
            await self.redis.eval(
                """
                if redis.call("GET", KEYS[1]) == ARGV[1] then
                    return redis.call("DEL", KEYS[1])
                end
                return 0
                """,
                1,
                lock_key,
                lock_token,
            )

    async def _listen(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue
                envelope = WebSocketEnvelope.model_validate_json(message["data"])
                connection_count = await connection_manager.count(envelope.game_id)
                logger.info(
                    "event_bus_received",
                    event_type=envelope.type,
                    game_id=envelope.game_id,
                    sequence=envelope.sequence,
                    connection_count=connection_count,
                )
                await connection_manager.broadcast(envelope)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("event_bus_listener_failed", channel=EVENT_CHANNEL)
            if self._pubsub:
                await self._pubsub.aclose()
                self._pubsub = None
            if self.redis:
                await self.redis.aclose()
                self.redis = None


event_bus = EventBus()
