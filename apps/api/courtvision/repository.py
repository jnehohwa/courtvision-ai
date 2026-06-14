from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Select, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from courtvision.models import (
    FeatureSnapshot,
    Game,
    PlayByPlayEvent,
    Prediction,
    SourceHealthRecord,
)
from courtvision.sources import SourceHealth


async def list_games(session: AsyncSession, game_date: date) -> list[Game]:
    start = datetime.combine(game_date, datetime.min.time(), tzinfo=UTC)
    end = datetime.combine(game_date, datetime.max.time(), tzinfo=UTC)
    statement = (
        select(Game)
        .where(Game.scheduled_at >= start, Game.scheduled_at <= end)
        .options(selectinload(Game.home_team), selectinload(Game.away_team))
        .order_by(Game.scheduled_at)
    )
    return list((await session.scalars(statement)).all())


async def get_game(session: AsyncSession, game_id: str) -> Game | None:
    statement = (
        select(Game)
        .where(Game.id == game_id)
        .options(selectinload(Game.home_team), selectinload(Game.away_team))
    )
    return await session.scalar(statement)


async def latest_prediction(
    session: AsyncSession,
    game_id: str,
    kind: str,
) -> Prediction | None:
    statement = (
        select(Prediction)
        .where(Prediction.game_id == game_id, Prediction.kind == kind)
        .order_by(desc(Prediction.predicted_at), desc(Prediction.id))
        .limit(1)
    )
    return await session.scalar(statement)


async def latest_feature_snapshot(
    session: AsyncSession,
    game_id: str,
    model_type: str,
    *,
    before: datetime,
) -> FeatureSnapshot | None:
    statement = (
        select(FeatureSnapshot)
        .where(
            FeatureSnapshot.game_id == game_id,
            FeatureSnapshot.model_type == model_type,
            FeatureSnapshot.feature_timestamp <= before,
        )
        .order_by(desc(FeatureSnapshot.feature_timestamp), desc(FeatureSnapshot.id))
        .limit(1)
    )
    return await session.scalar(statement)


async def game_events(
    session: AsyncSession,
    game_id: str,
    *,
    after_sequence: int = -1,
) -> list[PlayByPlayEvent]:
    latest_revision = (
        select(
            PlayByPlayEvent.source_event_id,
            func.max(PlayByPlayEvent.revision).label("latest_revision"),
        )
        .where(PlayByPlayEvent.game_id == game_id)
        .group_by(PlayByPlayEvent.source_event_id)
        .subquery()
    )
    statement: Select[tuple[PlayByPlayEvent]] = (
        select(PlayByPlayEvent)
        .join(
            latest_revision,
            (PlayByPlayEvent.source_event_id == latest_revision.c.source_event_id)
            & (PlayByPlayEvent.revision == latest_revision.c.latest_revision),
        )
        .where(
            PlayByPlayEvent.game_id == game_id,
            PlayByPlayEvent.sequence > after_sequence,
        )
        .order_by(PlayByPlayEvent.sequence)
    )
    return list((await session.scalars(statement)).all())


async def save_source_health(
    session: AsyncSession,
    health: SourceHealth,
) -> SourceHealthRecord:
    record = await session.get(SourceHealthRecord, health.source)
    if record is None:
        record = SourceHealthRecord(
            source=health.source,
            status=health.status,
            updated_at=datetime.now(UTC),
        )
        session.add(record)

    record.status = health.status
    record.last_attempt_at = health.last_attempt_at
    record.last_success_at = health.last_success_at
    record.last_event_at = health.last_event_at
    record.last_error = health.last_error
    record.consecutive_failures = health.consecutive_failures
    record.total_polls = health.total_polls
    record.total_events = health.total_events
    record.current_poll_interval_seconds = health.current_poll_interval_seconds
    record.updated_at = datetime.now(UTC)
    await session.flush()
    return record


async def list_source_health(session: AsyncSession) -> list[SourceHealthRecord]:
    return list(
        (
            await session.scalars(
                select(SourceHealthRecord).order_by(SourceHealthRecord.source)
            )
        ).all()
    )
