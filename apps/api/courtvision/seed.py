from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text

from courtvision.database import SessionFactory
from courtvision.fixtures import (
    PLAYERS,
    PREGAME_PROBABILITIES,
    TEAMS,
    fixture_events,
    fixture_games,
    fixture_shots,
    fixture_team_game_statistics,
)
from courtvision.model_contracts import (
    LIVE_WIN_CONTRACT,
    PREGAME_CONTRACT,
    SHOT_QUALITY_CONTRACT,
)
from courtvision.models import (
    FeatureSnapshot,
    Game,
    IngestionRun,
    ModelActivation,
    ModelVersion,
    PlayByPlayEvent,
    Player,
    Prediction,
    Shot,
    SourceHealthRecord,
    Team,
    TeamGameStatistic,
)


async def seed_database() -> None:
    games = fixture_games()
    events = fixture_events()
    team_statistics = fixture_team_game_statistics()
    shots = fixture_shots()

    async with SessionFactory() as session:
        if session.bind and session.bind.dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(20260614)"))

        for values in TEAMS:
            if await session.get(Team, values["id"]) is None:
                session.add(Team(**values))

        for values in PLAYERS:
            if await session.get(Player, values["id"]) is None:
                session.add(Player(**values))

        for values in games:
            if await session.get(Game, values["id"]) is None:
                session.add(Game(**values))

        await session.flush()

        for values in events:
            existing = await session.scalar(
                select(PlayByPlayEvent).where(
                    PlayByPlayEvent.game_id == values["game_id"],
                    PlayByPlayEvent.source_event_id == values["source_event_id"],
                    PlayByPlayEvent.revision == values["revision"],
                )
            )
            if existing is None:
                session.add(PlayByPlayEvent(**values))

        for values in team_statistics:
            existing = await session.scalar(
                select(TeamGameStatistic).where(
                    TeamGameStatistic.game_id == values["game_id"],
                    TeamGameStatistic.team_id == values["team_id"],
                )
            )
            if existing is None:
                session.add(TeamGameStatistic(**values))

        for values in shots:
            existing = await session.scalar(
                select(Shot).where(
                    Shot.game_id == values["game_id"],
                    Shot.source_shot_id == values["source_shot_id"],
                    Shot.revision == values["revision"],
                )
            )
            if existing is None:
                session.add(Shot(**values))

        model_specs = (
            PREGAME_CONTRACT,
            SHOT_QUALITY_CONTRACT,
            LIVE_WIN_CONTRACT,
        )
        now = datetime.now(UTC)
        for contract in model_specs:
            model_type = contract.model_type
            version = contract.baseline_version
            active = await session.scalar(
                select(ModelVersion).where(
                    ModelVersion.model_type == model_type,
                    ModelVersion.is_active.is_(True),
                )
            )
            existing = await session.scalar(
                select(ModelVersion).where(
                    ModelVersion.model_type == model_type,
                    ModelVersion.version == version,
                )
            )
            if existing is None:
                is_initial_active = active is None
                baseline_model = ModelVersion(
                    model_type=model_type,
                    version=version,
                    feature_schema={
                        "features": list(contract.features),
                        "schema_version": contract.schema_version,
                    },
                    metrics={
                        "status": "fixture_baseline",
                        "brier_score": 0.25,
                        "log_loss": 0.69,
                        "expected_calibration_error": 0.04,
                    },
                    dataset_version="synthetic-fixture-1.0",
                    status="active" if is_initial_active else "retired",
                    is_active=is_initial_active,
                    registered_at=now,
                    activated_at=now if is_initial_active else None,
                    promotion_metadata={"source": "synthetic-fixture"},
                )
                session.add(baseline_model)
                if is_initial_active:
                    await session.flush()
                    session.add(
                        ModelActivation(
                            model_type=model_type,
                            model_version=version,
                            previous_model_version=None,
                            action="seed",
                            reason="initial synthetic fixture baseline",
                            activated_at=now,
                            metrics_snapshot={
                                "brier_score": 0.25,
                                "log_loss": 0.69,
                                "expected_calibration_error": 0.04,
                            },
                        )
                    )
            else:
                existing.feature_schema = {
                    "features": list(contract.features),
                    "schema_version": contract.schema_version,
                }
                existing.metrics = {
                    "status": "fixture_baseline",
                    "brier_score": 0.25,
                    "log_loss": 0.69,
                    "expected_calibration_error": 0.04,
                }
                existing.dataset_version = "synthetic-fixture-1.0"
                if active is None:
                    existing.status = "active"
                    existing.is_active = True
                    existing.activated_at = existing.activated_at or now
                    session.add(
                        ModelActivation(
                            model_type=model_type,
                            model_version=version,
                            previous_model_version=None,
                            action="seed",
                            reason="restored synthetic fixture baseline",
                            activated_at=now,
                            metrics_snapshot={
                                "brier_score": 0.25,
                                "log_loss": 0.69,
                                "expected_calibration_error": 0.04,
                            },
                        )
                    )

        statistics_by_game = {
            (row["game_id"], row["team_id"]): row for row in team_statistics
        }
        for game_id, probability in PREGAME_PROBABILITIES.items():
            game = await session.get(Game, game_id)
            assert game is not None
            home = statistics_by_game[(game_id, game.home_team_id)]
            away = statistics_by_game[(game_id, game.away_team_id)]
            feature_timestamp = game.scheduled_at - timedelta(hours=2)
            prediction_timestamp = game.scheduled_at - timedelta(hours=1)

            feature_snapshot = await session.scalar(
                select(FeatureSnapshot).where(
                    FeatureSnapshot.game_id == game_id,
                    FeatureSnapshot.model_type == "pregame",
                    FeatureSnapshot.feature_timestamp == feature_timestamp,
                    FeatureSnapshot.schema_version == PREGAME_CONTRACT.schema_version,
                )
            )
            feature_values = {
                "home_offensive_rating": home["offensive_rating"],
                "away_offensive_rating": away["offensive_rating"],
                "home_defensive_rating": home["defensive_rating"],
                "away_defensive_rating": away["defensive_rating"],
                "home_pace": home["pace"],
                "away_pace": away["pace"],
                "home_rest_days": home["rest_days"],
                "away_rest_days": away["rest_days"],
            }
            if feature_snapshot is None:
                session.add(
                    FeatureSnapshot(
                        game_id=game_id,
                        model_type="pregame",
                        feature_timestamp=feature_timestamp,
                        prediction_timestamp=prediction_timestamp,
                        schema_version=PREGAME_CONTRACT.schema_version,
                        dataset_version="synthetic-fixture-1.0",
                        features=feature_values,
                        provenance={
                            "source": "synthetic-fixture",
                            "window_games": 10,
                        },
                    )
                )
            else:
                feature_snapshot.prediction_timestamp = prediction_timestamp
                feature_snapshot.features = feature_values

            existing = await session.scalar(
                select(Prediction).where(
                    Prediction.game_id == game_id,
                    Prediction.kind == "pregame",
                )
            )
            if existing is None:
                session.add(
                    Prediction(
                        game_id=game_id,
                        kind="pregame",
                        home_probability=probability,
                        model_version="pregame-logistic-baseline-1.0",
                        feature_timestamp=feature_timestamp,
                        predicted_at=prediction_timestamp,
                        metadata_json={"confidence": "calibrated baseline"},
                    )
                )
            else:
                existing.model_version = "pregame-logistic-baseline-1.0"

        last_run = await session.scalar(
            select(IngestionRun).where(IngestionRun.source == "synthetic-fixture")
        )
        if last_run is None:
            session.add(
                IngestionRun(
                    source="synthetic-fixture",
                    status="completed",
                    started_at=now - timedelta(seconds=1),
                    completed_at=now,
                    records_seen=len(events) + len(team_statistics) + len(shots),
                    records_written=len(events) + len(team_statistics) + len(shots),
                )
            )

        replay_health = await session.get(SourceHealthRecord, "replay")
        if replay_health is None:
            session.add(
                SourceHealthRecord(
                    source="replay",
                    status="healthy",
                    last_attempt_at=now,
                    last_success_at=now,
                    last_event_at=max(event["occurred_at"] for event in events),
                    consecutive_failures=0,
                    total_polls=1,
                    total_events=len(events),
                    current_poll_interval_seconds=None,
                    updated_at=now,
                )
            )
        else:
            replay_health.status = "healthy"
            replay_health.last_success_at = now
            replay_health.last_event_at = max(event["occurred_at"] for event in events)
            replay_health.total_events = len(events)
            replay_health.updated_at = now

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed_database())
