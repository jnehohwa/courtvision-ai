from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from courtvision.broadcast import event_bus
from courtvision.inference import active_model_resolver
from courtvision.models import Game, PlayByPlayEvent, Shot
from courtvision.prediction_runtime import resolve_pregame_estimate
from courtvision.presenters import event_envelopes
from courtvision.repository import get_game, latest_prediction
from courtvision.sources import PlayByPlaySourcePayload, SourceBatch, SourceEvent


@dataclass(frozen=True)
class IngestionResult:
    status: str
    event: PlayByPlayEvent | None
    shot: Shot | None = None


class PlayByPlayIngestor:
    async def ingest_batch(
        self,
        session: AsyncSession,
        *,
        game_id: str,
        batch: SourceBatch,
    ) -> list[IngestionResult]:
        results = []
        for source_event in batch.events:
            results.append(
                await self.ingest_event(
                    session,
                    game_id=game_id,
                    source_event=source_event,
                )
            )
        return results

    async def ingest_event(
        self,
        session: AsyncSession,
        *,
        game_id: str,
        source_event: SourceEvent,
    ) -> IngestionResult:
        payload = PlayByPlaySourcePayload.model_validate(source_event.payload)
        game = await session.scalar(
            select(Game).where(Game.id == game_id).with_for_update()
        )
        if game is None:
            raise ValueError(f"Game {game_id} does not exist")

        exact_revision = await session.scalar(
            select(PlayByPlayEvent).where(
                PlayByPlayEvent.game_id == game_id,
                PlayByPlayEvent.source_event_id == source_event.source_event_id,
                PlayByPlayEvent.revision == source_event.revision,
            )
        )
        if exact_revision is not None:
            return IngestionResult(status="duplicate", event=exact_revision)

        latest_revision = await session.scalar(
            select(PlayByPlayEvent)
            .where(
                PlayByPlayEvent.game_id == game_id,
                PlayByPlayEvent.source_event_id == source_event.source_event_id,
            )
            .order_by(desc(PlayByPlayEvent.revision))
            .limit(1)
        )
        if latest_revision is not None and source_event.revision < latest_revision.revision:
            return IngestionResult(status="stale", event=latest_revision)

        sequence = await self._allocate_sequence(
            session,
            game_id=game_id,
            requested_sequence=payload.sequence,
            is_correction=latest_revision is not None,
        )
        ingested_at = datetime.now(UTC)
        event = PlayByPlayEvent(
            game_id=game_id,
            source_event_id=source_event.source_event_id,
            sequence=sequence,
            revision=source_event.revision,
            event_type=payload.event_type,
            description=payload.description,
            period=payload.period,
            clock_seconds=payload.game_clock_seconds,
            home_score=payload.home_score,
            away_score=payload.away_score,
            possession_team_id=payload.possession_team_id,
            home_fouls=payload.home_fouls,
            away_fouls=payload.away_fouls,
            x=payload.x,
            y=payload.y,
            shot_value=payload.shot_value,
            occurred_at=source_event.occurred_at,
            ingested_at=ingested_at,
            raw_payload=source_event.model_dump(mode="json"),
        )
        session.add(event)
        await session.flush()

        shot = self._make_shot(
            game_id=game_id,
            source_event=source_event,
            payload=payload,
            sequence=sequence,
            ingested_at=ingested_at,
        )
        if shot is not None:
            session.add(shot)
            await session.flush()

        if self._is_current_or_newer_state(game, payload):
            game.home_score = payload.home_score
            game.away_score = payload.away_score
            game.period = payload.period
            game.clock_seconds = payload.game_clock_seconds
            game.status = payload.game_status
        game.source_status = "delayed"
        game.last_ingested_at = ingested_at

        return IngestionResult(
            status="corrected" if latest_revision is not None else "added",
            event=event,
            shot=shot,
        )

    @staticmethod
    def _is_current_or_newer_state(
        game: Game,
        payload: PlayByPlaySourcePayload,
    ) -> bool:
        if payload.period != game.period:
            return payload.period > game.period
        return payload.game_clock_seconds <= game.clock_seconds

    async def publish_results(
        self,
        session: AsyncSession,
        *,
        game_id: str,
        results: list[IngestionResult],
    ) -> None:
        game = await get_game(session, game_id)
        if game is None:
            return
        prediction = await latest_prediction(session, game_id, "pregame")
        baseline = 0.5
        if prediction is not None:
            pregame_runtime = await active_model_resolver.resolve(
                session,
                "pregame",
            )
            estimate = await resolve_pregame_estimate(
                session,
                prediction,
                pregame_runtime,
            )
            baseline = estimate.probability
        live_runtime = await active_model_resolver.resolve(session, "live_win")

        published_events = []
        event_types = []
        for result in results:
            if result.status not in {"added", "corrected"} or result.event is None:
                continue
            published_events.append(result.event)
            event_types.append(
                "play_corrected"
                if result.status == "corrected"
                else "play_added"
            )
        envelopes = await event_envelopes(
            published_events,
            game,
            baseline,
            event_types=event_types,
            runtime=live_runtime,
        )
        for envelope in envelopes:
            await event_bus.publish(envelope)

    async def _allocate_sequence(
        self,
        session: AsyncSession,
        *,
        game_id: str,
        requested_sequence: int,
        is_correction: bool,
    ) -> int:
        maximum = await session.scalar(
            select(func.max(PlayByPlayEvent.sequence)).where(
                PlayByPlayEvent.game_id == game_id
            )
        )
        maximum = maximum or 0
        collision = await session.scalar(
            select(PlayByPlayEvent.id).where(
                PlayByPlayEvent.game_id == game_id,
                PlayByPlayEvent.sequence == requested_sequence,
            )
        )
        if is_correction or collision is not None or requested_sequence <= maximum:
            return maximum + 1
        return requested_sequence

    def _make_shot(
        self,
        *,
        game_id: str,
        source_event: SourceEvent,
        payload: PlayByPlaySourcePayload,
        sequence: int,
        ingested_at: datetime,
    ) -> Shot | None:
        if (
            payload.event_type not in {"shot_made", "shot_missed"}
            or payload.x is None
            or payload.y is None
            or payload.shot_value is None
        ):
            return None

        distance = math.hypot(payload.x, payload.y)
        angle = abs(math.degrees(math.atan2(payload.x, max(payload.y, 0.1))))
        return Shot(
            game_id=game_id,
            source_shot_id=payload.source_shot_id or source_event.source_event_id,
            source_event_id=source_event.source_event_id,
            sequence=sequence,
            revision=source_event.revision,
            player_id=payload.player_id,
            team_id=payload.team_id,
            x=payload.x,
            y=payload.y,
            distance_feet=round(distance, 3),
            angle_degrees=round(angle, 3),
            shot_value=payload.shot_value,
            made=payload.event_type == "shot_made",
            period=payload.period,
            game_clock_seconds=payload.game_clock_seconds,
            score_differential=payload.home_score - payload.away_score,
            occurred_at=source_event.occurred_at,
            ingested_at=ingested_at,
            raw_payload=source_event.model_dump(mode="json"),
        )


play_by_play_ingestor = PlayByPlayIngestor()
