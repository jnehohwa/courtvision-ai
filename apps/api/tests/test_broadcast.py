from __future__ import annotations

from datetime import UTC, datetime

from courtvision import broadcast
from courtvision.broadcast import ConnectionManager, EventBus
from courtvision.schemas import WebSocketEnvelope


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict[str, object]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)


def envelope(sequence: int, event_type: str = "play_added") -> WebSocketEnvelope:
    now = datetime.now(UTC)
    return WebSocketEnvelope(
        type=event_type,
        game_id="cv-2026-bos-nyk",
        sequence=sequence,
        occurred_at=now,
        ingested_at=now,
        source_status="replay",
        model_version="live-win-logistic-baseline-1.0",
        payload={"status": event_type},
    )


async def test_connection_manager_tracks_highest_delivered_sequence():
    manager = ConnectionManager()
    websocket = FakeWebSocket()

    await manager.connect("cv-2026-bos-nyk", websocket)
    await manager.broadcast(envelope(7))
    await manager.broadcast(envelope(3, event_type="source_status"))

    assert websocket.accepted
    assert [message["sequence"] for message in websocket.sent] == [7, 3]
    assert await manager.last_sequence(websocket) == 7

    await manager.disconnect("cv-2026-bos-nyk", websocket)
    assert await manager.last_sequence(websocket, default=-1) == -1


async def test_event_bus_redis_client_allows_idle_blocking_commands(monkeypatch):
    calls: list[dict[str, object]] = []

    class FakeRedis:
        async def ping(self) -> None:
            return None

        async def aclose(self) -> None:
            return None

    class FakeRedisFactory:
        @staticmethod
        def from_url(url: str, **kwargs: object) -> FakeRedis:
            calls.append({"url": url, **kwargs})
            return FakeRedis()

    monkeypatch.setattr(broadcast, "Redis", FakeRedisFactory)

    bus = EventBus()
    try:
        assert await bus.start(subscribe=False)
    finally:
        await bus.stop()

    assert calls
    assert calls[0]["socket_connect_timeout"] == 0.5
    assert calls[0]["socket_timeout"] is None
    assert calls[0]["decode_responses"] is True
