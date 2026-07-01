from __future__ import annotations

from courtvision import broadcast
from courtvision.broadcast import EventBus


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
