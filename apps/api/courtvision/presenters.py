from __future__ import annotations

from datetime import UTC, datetime

from courtvision.ml import LiveGameState, prediction_service
from courtvision.models import Game, PlayByPlayEvent, Prediction
from courtvision.schemas import (
    GameResponse,
    PlayPayload,
    PredictionResponse,
    TeamResponse,
    TimelinePoint,
    WebSocketEnvelope,
)


def prediction_response(prediction: Prediction) -> PredictionResponse:
    return PredictionResponse(
        game_id=prediction.game_id,
        kind=prediction.kind,
        home_probability=round(prediction.home_probability, 4),
        away_probability=round(1 - prediction.home_probability, 4),
        model_version=prediction.model_version,
        predicted_at=prediction.predicted_at,
        feature_timestamp=prediction.feature_timestamp,
        confidence=prediction.metadata_json.get("confidence", "calibrated baseline"),
    )


def game_response(game: Game, prediction: Prediction | None = None) -> GameResponse:
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
        prediction=prediction_response(prediction) if prediction else None,
    )


def live_home_probability(event: PlayByPlayEvent, game: Game, baseline: float) -> float:
    time_remaining = max((4 - event.period) * 720 + event.clock_seconds, 0)
    state = LiveGameState(
        score_differential=event.home_score - event.away_score,
        time_remaining_seconds=time_remaining,
        possession_is_home=event.possession_team_id == game.home_team_id,
        home_fouls=event.home_fouls,
        away_fouls=event.away_fouls,
        pregame_home_probability=baseline,
    )
    return prediction_service.live_probability(state)


def timeline_point(
    event: PlayByPlayEvent,
    game: Game,
    baseline: float,
) -> TimelinePoint:
    return TimelinePoint(
        sequence=event.sequence,
        period=event.period,
        clock_seconds=event.clock_seconds,
        home_probability=round(live_home_probability(event, game, baseline), 4),
        description=event.description,
        event_type=event.event_type,
        home_score=event.home_score,
        away_score=event.away_score,
        x=event.x,
        y=event.y,
        shot_value=event.shot_value,
    )


def event_envelope(
    event: PlayByPlayEvent,
    game: Game,
    baseline: float,
    *,
    event_type: str = "play_added",
) -> WebSocketEnvelope:
    probability = live_home_probability(event, game, baseline)
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
        home_probability=round(probability, 4),
    )
    return WebSocketEnvelope(
        type=event_type,
        game_id=game.id,
        sequence=event.sequence,
        occurred_at=event.occurred_at,
        ingested_at=event.ingested_at,
        source_status=game.source_status,
        model_version=prediction_service.live_model_version,
        payload=payload.model_dump(mode="json"),
    )


def status_envelope(
    game: Game,
    *,
    sequence: int,
    event_type: str,
    payload: dict[str, object],
) -> WebSocketEnvelope:
    now = datetime.now(UTC)
    return WebSocketEnvelope(
        type=event_type,
        game_id=game.id,
        sequence=sequence,
        occurred_at=now,
        ingested_at=now,
        source_status=game.source_status,
        model_version=prediction_service.live_model_version,
        payload=payload,
    )
