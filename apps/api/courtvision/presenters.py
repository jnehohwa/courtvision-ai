from __future__ import annotations

from datetime import UTC, datetime

from courtvision.inference import LoadedModel
from courtvision.ml import LiveGameState, ProbabilityEstimate, prediction_service
from courtvision.models import Game, PlayByPlayEvent, Prediction
from courtvision.schemas import (
    GameResponse,
    PlayPayload,
    PredictionResponse,
    TeamResponse,
    TimelinePoint,
    WebSocketEnvelope,
)


def prediction_response(
    prediction: Prediction,
    estimate: ProbabilityEstimate | None = None,
) -> PredictionResponse:
    probability = estimate.probability if estimate else prediction.home_probability
    return PredictionResponse(
        game_id=prediction.game_id,
        kind=prediction.kind,
        home_probability=round(probability, 4),
        away_probability=round(1 - probability, 4),
        model_version=estimate.model_version if estimate else prediction.model_version,
        predicted_at=prediction.predicted_at,
        feature_timestamp=prediction.feature_timestamp,
        confidence=(
            "active calibrated artifact"
            if estimate and estimate.used_artifact
            else prediction.metadata_json.get("confidence", "calibrated baseline")
        ),
    )


def game_response(
    game: Game,
    prediction: Prediction | PredictionResponse | None = None,
) -> GameResponse:
    presented_prediction = (
        prediction
        if isinstance(prediction, PredictionResponse)
        else prediction_response(prediction) if prediction else None
    )
    return GameResponse(
        id=game.id,
        scheduled_at=game.scheduled_at,
        home_team=TeamResponse.model_validate(game.home_team, from_attributes=True),
        away_team=TeamResponse.model_validate(game.away_team, from_attributes=True),
        home_score=game.home_score,
        away_score=game.away_score,
        period=game.period,
        clock_seconds=game.clock_seconds,
        status=game.status,
        source_status=game.source_status,
        last_ingested_at=game.last_ingested_at,
        prediction=presented_prediction,
    )


def live_game_state(
    event: PlayByPlayEvent,
    game: Game,
    baseline: float,
) -> LiveGameState:
    time_remaining = max((4 - event.period) * 720 + event.clock_seconds, 0)
    return LiveGameState(
        score_differential=event.home_score - event.away_score,
        time_remaining_seconds=time_remaining,
        possession_is_home=event.possession_team_id == game.home_team_id,
        home_fouls=event.home_fouls,
        away_fouls=event.away_fouls,
        pregame_home_probability=baseline,
    )


async def live_home_estimate(
    event: PlayByPlayEvent,
    game: Game,
    baseline: float,
    runtime: LoadedModel | None = None,
) -> ProbabilityEstimate:
    return (
        await prediction_service.live_estimates(
            [live_game_state(event, game, baseline)],
            runtime,
        )
    )[0]


async def timeline_points(
    events: list[PlayByPlayEvent],
    game: Game,
    baseline: float,
    runtime: LoadedModel | None = None,
) -> tuple[str, list[TimelinePoint]]:
    if not events:
        version = runtime.version if runtime else prediction_service.live_model_version
        return version, []
    estimates = await prediction_service.live_estimates(
        [live_game_state(event, game, baseline) for event in events],
        runtime,
    )
    points = [
        _timeline_point(event, estimate)
        for event, estimate in zip(events, estimates, strict=True)
    ]
    return estimates[0].model_version, points


async def timeline_point(
    event: PlayByPlayEvent,
    game: Game,
    baseline: float,
    runtime: LoadedModel | None = None,
) -> TimelinePoint:
    return _timeline_point(
        event,
        await live_home_estimate(event, game, baseline, runtime),
    )


def _timeline_point(
    event: PlayByPlayEvent,
    estimate: ProbabilityEstimate,
) -> TimelinePoint:
    return TimelinePoint(
        sequence=event.sequence,
        period=event.period,
        clock_seconds=event.clock_seconds,
        home_probability=round(estimate.probability, 4),
        description=event.description,
        event_type=event.event_type,
        home_score=event.home_score,
        away_score=event.away_score,
        x=event.x,
        y=event.y,
        shot_value=event.shot_value,
    )


async def event_envelope(
    event: PlayByPlayEvent,
    game: Game,
    baseline: float,
    *,
    event_type: str = "play_added",
    runtime: LoadedModel | None = None,
) -> WebSocketEnvelope:
    return (
        await event_envelopes(
            [event],
            game,
            baseline,
            event_types=[event_type],
            runtime=runtime,
        )
    )[0]


async def event_envelopes(
    events: list[PlayByPlayEvent],
    game: Game,
    baseline: float,
    *,
    event_types: list[str] | None = None,
    runtime: LoadedModel | None = None,
) -> list[WebSocketEnvelope]:
    if not events:
        return []
    if event_types is not None and len(event_types) != len(events):
        raise ValueError("Event type count must match the event count")
    estimates = await prediction_service.live_estimates(
        [live_game_state(event, game, baseline) for event in events],
        runtime,
    )
    return [
        _event_envelope(
            event,
            game,
            estimate,
            event_type=event_types[index] if event_types else "play_added",
        )
        for index, (event, estimate) in enumerate(
            zip(events, estimates, strict=True)
        )
    ]


def _event_envelope(
    event: PlayByPlayEvent,
    game: Game,
    estimate: ProbabilityEstimate,
    *,
    event_type: str,
) -> WebSocketEnvelope:
    payload = PlayPayload(
        sequence=event.sequence,
        source_event_id=event.source_event_id,
        revision=event.revision,
        event_type=event.event_type,
        description=event.description,
        period=event.period,
        clock_seconds=event.clock_seconds,
        home_score=event.home_score,
        away_score=event.away_score,
        possession_team_id=event.possession_team_id,
        home_fouls=event.home_fouls,
        away_fouls=event.away_fouls,
        x=event.x,
        y=event.y,
        shot_value=event.shot_value,
        home_probability=round(estimate.probability, 4),
    )
    return WebSocketEnvelope(
        type=event_type,
        game_id=game.id,
        sequence=event.sequence,
        occurred_at=event.occurred_at,
        ingested_at=event.ingested_at,
        source_status=game.source_status,
        model_version=estimate.model_version,
        payload=payload.model_dump(mode="json"),
    )


def status_envelope(
    game: Game,
    *,
    sequence: int,
    event_type: str,
    payload: dict[str, object],
    model_version: str | None = None,
) -> WebSocketEnvelope:
    now = datetime.now(UTC)
    return WebSocketEnvelope(
        type=event_type,
        game_id=game.id,
        sequence=sequence,
        occurred_at=now,
        ingested_at=now,
        source_status=game.source_status,
        model_version=model_version or prediction_service.live_model_version,
        payload=payload,
    )
