from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from courtvision.database import SessionFactory
from courtvision.ingest import run_ingestion
from courtvision.models import SourceHealthRecord
from courtvision.sources import (
    AdaptivePollingPolicy,
    BasketballDataSource,
    DelayedLiveSource,
    HistoricalNbaSource,
    RetryPolicy,
    SourceBatch,
    SourceDisabledError,
    SourceEvent,
    SourcePoller,
    SourceValidationError,
    PlayByPlaySourcePayload,
)


def source_event(identifier: str) -> SourceEvent:
    return SourceEvent(
        source_event_id=identifier,
        payload={"id": identifier},
        occurred_at=datetime.now(UTC),
    )


async def test_historical_source_paginates_recorded_events():
    source = HistoricalNbaSource(
        {"game-1": [source_event("one"), source_event("two")]},
        page_size=1,
    )

    first = await source.fetch("game-1")
    second = await source.fetch("game-1", first.next_cursor)

    assert [event.source_event_id for event in first.events] == ["one"]
    assert first.has_more
    assert [event.source_event_id for event in second.events] == ["two"]
    assert not second.has_more


async def test_source_schema_rejects_naive_timestamps():
    source = HistoricalNbaSource(
        {
            "game-1": [
                {
                    "source_event_id": "event-1",
                    "payload": {},
                    "occurred_at": datetime.now(),
                }
            ]
        }
    )

    with pytest.raises(SourceValidationError):
        await source.fetch("game-1")


def test_play_by_play_schema_requires_complete_shot_context():
    with pytest.raises(ValueError, match="shot events require"):
        PlayByPlaySourcePayload.model_validate(
            {
                "sequence": 1,
                "event_type": "shot_made",
                "description": "Incomplete shot",
                "period": 1,
                "game_clock_seconds": 700,
                "home_score": 2,
                "away_score": 0,
            }
        )


class FlakySource(BasketballDataSource):
    name = "flaky"

    def __init__(self) -> None:
        self.attempts = 0

    async def fetch(self, game_id: str, cursor: str | None = None) -> SourceBatch:
        self.attempts += 1
        if self.attempts < 3:
            raise httpx.ReadTimeout("temporary timeout")
        return SourceBatch(events=[source_event("recovered")])


async def test_poller_retries_with_bounded_exponential_backoff():
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    source = FlakySource()
    poller = SourcePoller(
        source,
        retry_policy=RetryPolicy(
            max_attempts=3,
            base_delay_seconds=0.25,
            max_delay_seconds=1,
            jitter_ratio=0,
        ),
        sleep=record_delay,
    )

    batch = await poller.poll_once("game-1")

    assert source.attempts == 3
    assert delays == [0.25, 0.5]
    assert batch.events[0].source_event_id == "recovered"
    assert poller.health.status == "healthy"
    assert poller.health.total_polls == 3
    assert poller.health.total_events == 1


async def test_disabled_source_is_not_retried():
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    poller = SourcePoller(
        DelayedLiveSource(enabled=False),
        sleep=record_delay,
    )

    with pytest.raises(SourceDisabledError):
        await poller.poll_once("game-1")

    assert delays == []
    assert poller.health.status == "disabled"
    assert poller.health.total_polls == 1


def test_adaptive_polling_slows_on_idle_and_failure():
    policy = AdaptivePollingPolicy(
        active_interval_seconds=5,
        idle_interval_seconds=10,
        error_interval_seconds=20,
        maximum_interval_seconds=60,
    )

    assert policy.next_interval(
        event_count=2,
        consecutive_empty_polls=0,
        consecutive_failures=0,
    ) == 5
    assert policy.next_interval(
        event_count=0,
        consecutive_empty_polls=3,
        consecutive_failures=0,
    ) == 30
    assert policy.next_interval(
        event_count=0,
        consecutive_empty_polls=0,
        consecutive_failures=3,
    ) == 60


async def test_ingestion_persists_disabled_source_health():
    await run_ingestion()

    async with SessionFactory() as session:
        health = await session.scalar(
            select(SourceHealthRecord).where(
                SourceHealthRecord.source == "delayed-live"
            )
        )

    assert health is not None
    assert health.status == "disabled"
    assert health.total_polls == 1
