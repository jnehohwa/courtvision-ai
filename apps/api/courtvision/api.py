from __future__ import annotations

import asyncio
import secrets
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from courtvision.broadcast import connection_manager, event_bus
from courtvision.config import settings
from courtvision.database import get_session
from courtvision.inference import active_model_resolver
from courtvision.ml import prediction_service
from courtvision.models import IngestionRun
from courtvision.prediction_runtime import resolve_pregame_estimate
from courtvision.presenters import (
    event_envelopes,
    game_response,
    prediction_response,
    status_envelope,
    timeline_points,
)
from courtvision.replay import replay_coordinator
from courtvision.repository import (
    game_events,
    get_game,
    latest_prediction,
    list_games,
    list_source_health,
)
from courtvision.schemas import (
    GamesResponse,
    GameResponse,
    HealthResponse,
    LiveSnapshotResponse,
    PredictionResponse,
    ReplayStartResponse,
    SourceHealthResponse,
    ShotQualityRequest,
    ShotQualityResponse,
)

api_router = APIRouter(prefix="/api/v1")
internal_router = APIRouter(prefix="/internal")


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@api_router.get("/games", response_model=GamesResponse)
async def games(
    game_date: date = Query(alias="date"),
    session: AsyncSession = Depends(get_session),
) -> GamesResponse:
    records = await list_games(session, game_date)
    pregame_runtime = await active_model_resolver.resolve(session, "pregame")
    responses = []
    for game in records:
        prediction = await latest_prediction(session, game.id, "pregame")
        presented_prediction = None
        if prediction is not None:
            estimate = await resolve_pregame_estimate(
                session,
                prediction,
                pregame_runtime,
            )
            presented_prediction = prediction_response(prediction, estimate)
        responses.append(game_response(game, presented_prediction))
    return GamesResponse(date=game_date, games=responses)


@api_router.get("/games/{game_id}", response_model=GameResponse)
async def game_detail(
    game_id: str,
    session: AsyncSession = Depends(get_session),
) -> GameResponse:
    game = await get_game(session, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    prediction = await latest_prediction(session, game_id, "pregame")
    presented_prediction = None
    if prediction is not None:
        runtime = await active_model_resolver.resolve(session, "pregame")
        estimate = await resolve_pregame_estimate(session, prediction, runtime)
        presented_prediction = prediction_response(prediction, estimate)
    return game_response(game, presented_prediction)


@api_router.get("/games/{game_id}/prediction", response_model=PredictionResponse)
async def game_prediction(
    game_id: str,
    session: AsyncSession = Depends(get_session),
) -> PredictionResponse:
    prediction = await latest_prediction(session, game_id, "pregame")
    if prediction is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    runtime = await active_model_resolver.resolve(session, "pregame")
    estimate = await resolve_pregame_estimate(session, prediction, runtime)
    return prediction_response(prediction, estimate)


@api_router.get("/games/{game_id}/live", response_model=LiveSnapshotResponse)
async def live_snapshot(
    game_id: str,
    session: AsyncSession = Depends(get_session),
) -> LiveSnapshotResponse:
    game = await get_game(session, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    prediction = await latest_prediction(session, game_id, "pregame")
    presented_prediction = None
    baseline = 0.5
    if prediction is not None:
        pregame_runtime = await active_model_resolver.resolve(session, "pregame")
        pregame_estimate = await resolve_pregame_estimate(
            session,
            prediction,
            pregame_runtime,
        )
        presented_prediction = prediction_response(prediction, pregame_estimate)
        baseline = pregame_estimate.probability
    live_runtime = await active_model_resolver.resolve(session, "live_win")
    events = await game_events(session, game_id)
    live_model_version, timeline = await timeline_points(
        events,
        game,
        baseline,
        live_runtime,
    )
    now = datetime.now(UTC)
    lag_seconds = (
        max(0, int((now - as_utc(game.last_ingested_at)).total_seconds()))
        if game.last_ingested_at
        else None
    )
    is_stale = lag_seconds is None or (
        game.source_status != "replay" and lag_seconds > settings.stale_after_seconds
    )

    return LiveSnapshotResponse(
        game=game_response(game, presented_prediction),
        timeline=timeline,
        latest_sequence=events[-1].sequence if events else 0,
        source_label="Historical replay" if game.source_status == "replay" else "Delayed data",
        is_stale=is_stale,
        freshness_seconds=lag_seconds,
        live_model_version=live_model_version,
        snapshot_generated_at=now,
    )


@api_router.post("/shot-quality", response_model=ShotQualityResponse)
async def shot_quality(
    request: ShotQualityRequest,
    session: AsyncSession = Depends(get_session),
) -> ShotQualityResponse:
    runtime = await active_model_resolver.resolve(session, "shot_quality")
    model_version, attempts = await prediction_service.shot_quality_batch(
        request.attempts,
        runtime,
    )
    return ShotQualityResponse(
        player_id=request.player_id,
        definition=(
            "Shooter-neutral expected field-goal probability from location and game context. "
            "Player identity is attribution only."
        ),
        model_version=model_version,
        attempts=attempts,
    )


@internal_router.post(
    "/replays/{game_id}/start",
    response_model=ReplayStartResponse,
)
async def start_replay(
    game_id: str,
    x_internal_key: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
) -> ReplayStartResponse:
    if not secrets.compare_digest(x_internal_key, settings.internal_api_key):
        raise HTTPException(status_code=403, detail="Invalid internal API key")
    if await get_game(session, game_id) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    events = await game_events(session, game_id)
    event_count = len(events)
    if event_bus.redis:
        started = await event_bus.enqueue_replay(game_id, settings.replay_tick_seconds)
    else:
        started, event_count = await replay_coordinator.start(
            game_id,
            settings.replay_tick_seconds,
        )
    status = "started" if started else "already_running"
    return ReplayStartResponse(game_id=game_id, status=status, event_count=event_count)


async def websocket_game(websocket: WebSocket, game_id: str, after_sequence: int = -1) -> None:
    async with get_session_context() as session:
        game = await get_game(session, game_id)
        if game is None:
            await websocket.accept()
            await websocket.close(code=4404, reason="Game not found")
            return
        prediction = await latest_prediction(session, game_id, "pregame")
        baseline = 0.5
        if prediction is not None:
            pregame_runtime = await active_model_resolver.resolve(session, "pregame")
            pregame_estimate = await resolve_pregame_estimate(
                session,
                prediction,
                pregame_runtime,
            )
            baseline = pregame_estimate.probability
        live_runtime = await active_model_resolver.resolve(session, "live_win")
        backlog = await game_events(session, game_id, after_sequence=after_sequence)

    await connection_manager.connect(game_id, websocket)
    try:
        backlog_envelopes = await event_envelopes(
            backlog,
            game,
            baseline,
            runtime=live_runtime,
        )
        live_model_version = (
            backlog_envelopes[0].model_version
            if backlog_envelopes
            else (
                live_runtime.version
                if live_runtime
                else prediction_service.live_model_version
            )
        )
        for envelope in backlog_envelopes:
            await websocket.send_json(envelope.model_dump(mode="json"))
            await connection_manager.note_sequence(websocket, envelope.sequence)
        last_sequence = backlog[-1].sequence if backlog else max(after_sequence, 0)
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=15)
            except TimeoutError:
                last_sequence = await connection_manager.last_sequence(
                    websocket,
                    default=last_sequence,
                )
                await websocket.send_json(
                    status_envelope(
                        game,
                        sequence=last_sequence,
                        event_type="heartbeat",
                        payload={"status": "connected"},
                        model_version=live_model_version,
                    ).model_dump(mode="json")
                )
    except WebSocketDisconnect:
        await connection_manager.disconnect(game_id, websocket)


class get_session_context:
    async def __aenter__(self) -> AsyncSession:
        from courtvision.database import SessionFactory

        self.session = SessionFactory()
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.session.close()


async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    database_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        database_status = "unavailable"

    latest_run = await session.scalar(
        select(IngestionRun).order_by(desc(IngestionRun.completed_at)).limit(1)
    )
    latest_at = latest_run.completed_at if latest_run else None
    lag = int((datetime.now(UTC) - as_utc(latest_at)).total_seconds()) if latest_at else None

    redis_status = "not_required"
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.redis_url, socket_connect_timeout=0.25)
        await redis.ping()
        await redis.aclose()
        redis_status = "ok"
    except Exception:
        redis_status = "degraded"

    source_records = await list_source_health(session)
    return HealthResponse(
        status="ok" if database_status == "ok" else "degraded",
        database=database_status,
        redis=redis_status,
        latest_ingestion_at=latest_at,
        data_lag_seconds=lag,
        delayed_live_enabled=settings.enable_delayed_live,
        sources={
            record.source: SourceHealthResponse(
                status=record.status,
                last_attempt_at=record.last_attempt_at,
                last_success_at=record.last_success_at,
                last_event_at=record.last_event_at,
                last_error=record.last_error,
                consecutive_failures=record.consecutive_failures,
                total_polls=record.total_polls,
                total_events=record.total_events,
                current_poll_interval_seconds=record.current_poll_interval_seconds,
                updated_at=record.updated_at,
            )
            for record in source_records
        },
    )
