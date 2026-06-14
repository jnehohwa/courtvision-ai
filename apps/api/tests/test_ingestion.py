from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from courtvision.database import SessionFactory
from courtvision.ingestion_service import play_by_play_ingestor
from courtvision.models import (
    FeatureSnapshot,
    Game,
    PlayByPlayEvent,
    Shot,
    Team,
    TeamGameStatistic,
)
from courtvision.repository import game_events
from courtvision.seed import seed_database
from courtvision.sources import SourceBatch, SourceEvent


async def test_fixture_seed_is_idempotent():
    await seed_database()
    await seed_database()

    async with SessionFactory() as session:
        team_count = await session.scalar(select(func.count()).select_from(Team))
        event_count = await session.scalar(select(func.count()).select_from(PlayByPlayEvent))
        statistic_count = await session.scalar(
            select(func.count()).select_from(TeamGameStatistic)
        )
        shot_count = await session.scalar(select(func.count()).select_from(Shot))
        feature_count = await session.scalar(
            select(func.count()).select_from(FeatureSnapshot)
        )

    assert team_count == 6
    assert event_count == 20
    assert statistic_count == 6
    assert shot_count == 18
    assert feature_count == 3


async def test_feature_snapshots_precede_predictions():
    async with SessionFactory() as session:
        snapshots = list((await session.scalars(select(FeatureSnapshot))).all())

    assert len(snapshots) == 3
    assert all(
        snapshot.feature_timestamp < snapshot.prediction_timestamp
        for snapshot in snapshots
    )
    assert all(
        set(snapshot.features)
        == {
            "home_offensive_rating",
            "away_offensive_rating",
            "home_defensive_rating",
            "away_defensive_rating",
            "home_pace",
            "away_pace",
            "home_rest_days",
            "away_rest_days",
        }
        for snapshot in snapshots
    )


async def test_shots_are_normalized_from_play_by_play():
    async with SessionFactory() as session:
        shots = list(
            (
                await session.scalars(
                    select(Shot)
                    .where(Shot.game_id == "cv-2026-bos-nyk")
                    .order_by(Shot.sequence)
                )
            ).all()
        )

    assert len(shots) == 18
    assert shots[0].source_event_id == "fixture-play-001"
    assert shots[0].player_id == "p-tatum"
    assert shots[0].distance_feet > 0
    assert shots[0].shot_value in {2, 3}
    assert any(not shot.made for shot in shots)


async def test_latest_event_revision_reconciles_a_correction():
    async with SessionFactory() as session:
        original = await session.scalar(
            select(PlayByPlayEvent).where(
                PlayByPlayEvent.game_id == "cv-2026-bos-nyk",
                PlayByPlayEvent.source_event_id == "fixture-play-020",
            )
        )
        assert original is not None
        session.add(
            PlayByPlayEvent(
                game_id=original.game_id,
                source_event_id=original.source_event_id,
                sequence=21,
                revision=2,
                event_type=original.event_type,
                description="Corrected Tatum driving layup",
                period=original.period,
                clock_seconds=original.clock_seconds,
                home_score=original.home_score,
                away_score=original.away_score,
                possession_team_id=original.possession_team_id,
                home_fouls=original.home_fouls,
                away_fouls=original.away_fouls,
                x=original.x,
                y=original.y,
                shot_value=original.shot_value,
                occurred_at=original.occurred_at,
                ingested_at=datetime.now(UTC),
                raw_payload={"correction": True},
            )
        )
        await session.flush()

        events = await game_events(session, original.game_id)
        corrected = [event for event in events if event.source_event_id == original.source_event_id]

        assert len(corrected) == 1
        assert corrected[0].revision == 2
        assert corrected[0].sequence == 21
        await session.rollback()


async def test_source_ingestion_is_idempotent_and_sequences_corrections():
    occurred_at = datetime.now(UTC)
    payload = {
        "sequence": 21,
        "event_type": "shot_made",
        "description": "Provider Tatum corner three",
        "period": 4,
        "game_clock_seconds": 90,
        "home_score": 105,
        "away_score": 99,
        "possession_team_id": "nyk",
        "home_fouls": 4,
        "away_fouls": 5,
        "x": -22.0,
        "y": 4.0,
        "shot_value": 3,
        "source_shot_id": "provider-shot-021",
        "player_id": "p-tatum",
        "team_id": "bos",
    }

    async with SessionFactory() as session:
        added = await play_by_play_ingestor.ingest_event(
            session,
            game_id="cv-2026-bos-nyk",
            source_event=SourceEvent(
                source_event_id="provider-play-021",
                revision=1,
                payload=payload,
                occurred_at=occurred_at,
            ),
        )
        duplicate = await play_by_play_ingestor.ingest_event(
            session,
            game_id="cv-2026-bos-nyk",
            source_event=SourceEvent(
                source_event_id="provider-play-021",
                revision=1,
                payload=payload,
                occurred_at=occurred_at,
            ),
        )
        corrected = await play_by_play_ingestor.ingest_event(
            session,
            game_id="cv-2026-bos-nyk",
            source_event=SourceEvent(
                source_event_id="provider-play-021",
                revision=2,
                payload={**payload, "description": "Corrected provider Tatum corner three"},
                occurred_at=occurred_at,
            ),
        )

        assert added.status == "added"
        assert added.event is not None and added.event.sequence == 21
        assert added.shot is not None and added.shot.player_id == "p-tatum"
        assert duplicate.status == "duplicate"
        assert corrected.status == "corrected"
        assert corrected.event is not None and corrected.event.sequence == 22

        latest = await game_events(session, "cv-2026-bos-nyk")
        reconciled = [
            event
            for event in latest
            if event.source_event_id == "provider-play-021"
        ]
        assert len(reconciled) == 1
        assert reconciled[0].revision == 2
        await session.rollback()


async def test_out_of_order_batch_does_not_rewind_game_state():
    occurred_at = datetime.now(UTC)
    later_event = SourceEvent(
        source_event_id="provider-den-phx-002",
        revision=1,
        occurred_at=occurred_at,
        payload={
            "sequence": 2,
            "event_type": "turnover",
            "description": "Later first-quarter event",
            "period": 1,
            "game_clock_seconds": 600,
            "home_score": 4,
            "away_score": 2,
            "possession_team_id": "phx",
        },
    )
    earlier_event = SourceEvent(
        source_event_id="provider-den-phx-001",
        revision=1,
        occurred_at=occurred_at,
        payload={
            "sequence": 1,
            "event_type": "turnover",
            "description": "Earlier first-quarter event",
            "period": 1,
            "game_clock_seconds": 700,
            "home_score": 2,
            "away_score": 0,
            "possession_team_id": "den",
        },
    )

    async with SessionFactory() as session:
        await play_by_play_ingestor.ingest_batch(
            session,
            game_id="cv-2026-den-phx",
            batch=SourceBatch(events=[later_event, earlier_event]),
        )
        game = await session.get(Game, "cv-2026-den-phx")

        assert game is not None
        assert (game.period, game.clock_seconds) == (1, 600)
        assert (game.home_score, game.away_score) == (4, 2)
        await session.rollback()
