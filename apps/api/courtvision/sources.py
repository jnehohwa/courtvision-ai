from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from courtvision.config import settings


class SourceUnavailableError(RuntimeError):
    pass


class SourceDisabledError(RuntimeError):
    pass


class SourceValidationError(RuntimeError):
    pass


class SourceEvent(BaseModel):
    source_event_id: str = Field(min_length=1, max_length=80)
    revision: int = Field(default=1, ge=1)
    payload: dict[str, Any]
    occurred_at: datetime
    source_updated_at: datetime | None = None

    @field_validator("occurred_at", "source_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("source timestamps must include a timezone")
        return value


class SourceBatch(BaseModel):
    events: list[SourceEvent]
    next_cursor: str | None = None
    has_more: bool = False
    source_updated_at: datetime | None = None

    @field_validator("source_updated_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("source timestamps must include a timezone")
        return value


class PlayByPlaySourcePayload(BaseModel):
    sequence: int = Field(ge=0)
    event_type: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=255)
    period: int = Field(ge=1, le=8)
    game_clock_seconds: int = Field(ge=0, le=720)
    home_score: int = Field(ge=0)
    away_score: int = Field(ge=0)
    possession_team_id: str | None = Field(default=None, max_length=32)
    home_fouls: int = Field(default=0, ge=0, le=20)
    away_fouls: int = Field(default=0, ge=0, le=20)
    x: float | None = Field(default=None, ge=-25, le=25)
    y: float | None = Field(default=None, ge=0, le=47)
    shot_value: int | None = None
    source_shot_id: str | None = Field(default=None, max_length=80)
    player_id: str | None = Field(default=None, max_length=32)
    team_id: str | None = Field(default=None, max_length=32)
    game_status: str = Field(default="live", max_length=24)

    @model_validator(mode="after")
    def validate_shot_fields(self) -> PlayByPlaySourcePayload:
        is_shot = self.event_type in {"shot_made", "shot_missed"}
        shot_fields = (self.x, self.y, self.shot_value)
        if is_shot and any(value is None for value in shot_fields):
            raise ValueError("shot events require x, y, and shot_value")
        if self.shot_value is not None and self.shot_value not in {2, 3}:
            raise ValueError("shot_value must be 2 or 3")
        return self


class SourceProvider(Protocol):
    async def __call__(self, game_id: str, cursor: str | None) -> SourceBatch | dict[str, Any]:
        ...


class BasketballDataSource(ABC):
    name: str

    @abstractmethod
    async def fetch(self, game_id: str, cursor: str | None = None) -> SourceBatch:
        raise NotImplementedError

    async def events(self, game_id: str) -> AsyncIterator[SourceEvent]:
        cursor: str | None = None
        while True:
            batch = await self.fetch(game_id, cursor)
            for event in batch.events:
                yield event
            if not batch.has_more:
                return
            cursor = batch.next_cursor


class HistoricalNbaSource(BasketballDataSource):
    """Validated recorded historical payloads for reproducible imports."""

    name = "historical-nba"

    def __init__(
        self,
        recorded_events: Mapping[str, Sequence[SourceEvent | dict[str, Any]]] | None = None,
        *,
        page_size: int = 500,
    ) -> None:
        self._recorded_events = recorded_events or {}
        self._page_size = page_size

    async def fetch(self, game_id: str, cursor: str | None = None) -> SourceBatch:
        if game_id not in self._recorded_events:
            raise SourceUnavailableError(
                "No recorded historical payload is configured for this game"
            )

        start = int(cursor or 0)
        raw_events = self._recorded_events[game_id]
        page = raw_events[start : start + self._page_size]
        events = validate_source_events(page)
        next_offset = start + len(page)
        has_more = next_offset < len(raw_events)
        return SourceBatch(
            events=events,
            next_cursor=str(next_offset) if has_more else None,
            has_more=has_more,
            source_updated_at=max(
                (event.source_updated_at or event.occurred_at for event in events),
                default=None,
            ),
        )


class DelayedLiveSource(BasketballDataSource):
    name = "delayed-live"

    def __init__(
        self,
        provider: SourceProvider | None = None,
        *,
        enabled: bool | None = None,
    ) -> None:
        self._provider = provider
        self._enabled = settings.enable_delayed_live if enabled is None else enabled

    async def fetch(self, game_id: str, cursor: str | None = None) -> SourceBatch:
        if not self._enabled:
            raise SourceDisabledError(
                "Delayed live polling is disabled by COURTVISION_ENABLE_DELAYED_LIVE"
            )
        if self._provider is None:
            raise SourceUnavailableError("No delayed provider is configured")

        try:
            payload = await self._provider(game_id, cursor)
            return payload if isinstance(payload, SourceBatch) else SourceBatch.model_validate(payload)
        except ValidationError as exc:
            raise SourceValidationError("Delayed provider returned an invalid schema") from exc


class ReplaySource(HistoricalNbaSource):
    name = "replay"

    def __init__(
        self,
        events: Sequence[SourceEvent | dict[str, Any]],
        *,
        tick_seconds: float | None = None,
    ) -> None:
        super().__init__({"replay": events}, page_size=1)
        self._tick_seconds = (
            settings.replay_tick_seconds if tick_seconds is None else tick_seconds
        )

    async def fetch(self, game_id: str, cursor: str | None = None) -> SourceBatch:
        await asyncio.sleep(self._tick_seconds)
        return await super().fetch("replay", cursor)


def validate_source_events(
    events: Sequence[SourceEvent | dict[str, Any]],
) -> list[SourceEvent]:
    validated: list[SourceEvent] = []
    try:
        for event in events:
            validated.append(
                event if isinstance(event, SourceEvent) else SourceEvent.model_validate(event)
            )
    except ValidationError as exc:
        raise SourceValidationError("Source event failed schema validation") from exc

    identifiers = [(event.source_event_id, event.revision) for event in validated]
    if len(identifiers) != len(set(identifiers)):
        raise SourceValidationError("A source batch contains duplicate event revisions")
    return validated


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    jitter_ratio: float = 0.15

    def delay_for(self, attempt: int, *, random_value: float | None = None) -> float:
        exponential = min(
            self.base_delay_seconds * 2 ** max(attempt - 1, 0),
            self.max_delay_seconds,
        )
        jitter_sample = random.random() if random_value is None else random_value
        jitter = exponential * self.jitter_ratio * ((jitter_sample * 2) - 1)
        return max(0, exponential + jitter)


@dataclass(frozen=True)
class AdaptivePollingPolicy:
    active_interval_seconds: float = 5.0
    idle_interval_seconds: float = 15.0
    error_interval_seconds: float = 30.0
    maximum_interval_seconds: float = 90.0

    def next_interval(
        self,
        *,
        event_count: int,
        consecutive_empty_polls: int,
        consecutive_failures: int,
    ) -> float:
        if consecutive_failures:
            return min(
                self.error_interval_seconds * 2 ** (consecutive_failures - 1),
                self.maximum_interval_seconds,
            )
        if event_count:
            return self.active_interval_seconds
        return min(
            self.idle_interval_seconds * max(consecutive_empty_polls, 1),
            self.maximum_interval_seconds,
        )


@dataclass
class SourceHealth:
    source: str
    status: str = "idle"
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_event_at: datetime | None = None
    last_error: str | None = None
    consecutive_failures: int = 0
    total_polls: int = 0
    total_events: int = 0
    current_poll_interval_seconds: float | None = None


HealthRecorder = Callable[[SourceHealth], Awaitable[None]]
SleepFunction = Callable[[float], Awaitable[None]]


class SourcePoller:
    transient_errors = (
        httpx.TimeoutException,
        httpx.TransportError,
        SourceUnavailableError,
    )

    def __init__(
        self,
        source: BasketballDataSource,
        *,
        retry_policy: RetryPolicy | None = None,
        polling_policy: AdaptivePollingPolicy | None = None,
        health_recorder: HealthRecorder | None = None,
        sleep: SleepFunction = asyncio.sleep,
    ) -> None:
        self.source = source
        self.retry_policy = retry_policy or RetryPolicy()
        self.polling_policy = polling_policy or AdaptivePollingPolicy()
        self.health_recorder = health_recorder
        self.sleep = sleep
        self.health = SourceHealth(source=source.name)
        self._empty_polls = 0

    async def poll_once(self, game_id: str, cursor: str | None = None) -> SourceBatch:
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            self.health.last_attempt_at = datetime.now(UTC)
            self.health.total_polls += 1
            try:
                batch = await self.source.fetch(game_id, cursor)
            except SourceDisabledError as exc:
                self.health.status = "disabled"
                self.health.last_error = str(exc)
                self.health.current_poll_interval_seconds = None
                await self._record_health()
                raise
            except SourceValidationError as exc:
                await self._record_failure(exc, retrying=False)
                raise
            except self.transient_errors as exc:
                retrying = attempt < self.retry_policy.max_attempts
                await self._record_failure(exc, retrying=retrying)
                if not retrying:
                    raise
                await self.sleep(self.retry_policy.delay_for(attempt))
                continue

            self.health.status = "healthy"
            self.health.last_success_at = datetime.now(UTC)
            self.health.last_error = None
            self.health.consecutive_failures = 0
            self.health.total_events += len(batch.events)
            if batch.events:
                self._empty_polls = 0
                self.health.last_event_at = max(event.occurred_at for event in batch.events)
            else:
                self._empty_polls += 1
            self.health.current_poll_interval_seconds = self.polling_policy.next_interval(
                event_count=len(batch.events),
                consecutive_empty_polls=self._empty_polls,
                consecutive_failures=0,
            )
            await self._record_health()
            return batch

        raise RuntimeError("unreachable")

    async def stream(
        self,
        game_id: str,
        *,
        cursor: str | None = None,
    ) -> AsyncIterator[SourceBatch]:
        next_cursor = cursor
        while True:
            try:
                batch = await self.poll_once(game_id, next_cursor)
            except self.transient_errors:
                interval = self.polling_policy.next_interval(
                    event_count=0,
                    consecutive_empty_polls=self._empty_polls,
                    consecutive_failures=self.health.consecutive_failures,
                )
                self.health.current_poll_interval_seconds = interval
                await self._record_health()
                await self.sleep(interval)
                continue

            yield batch
            if batch.next_cursor is not None:
                next_cursor = batch.next_cursor
            await self.sleep(self.health.current_poll_interval_seconds or 0)

    async def _record_failure(self, error: Exception, *, retrying: bool) -> None:
        self.health.status = "retrying" if retrying else "unavailable"
        self.health.last_error = str(error)
        self.health.consecutive_failures += 1
        self.health.current_poll_interval_seconds = self.polling_policy.next_interval(
            event_count=0,
            consecutive_empty_polls=self._empty_polls,
            consecutive_failures=self.health.consecutive_failures,
        )
        await self._record_health()

    async def _record_health(self) -> None:
        if self.health_recorder:
            await self.health_recorder(self.health)
