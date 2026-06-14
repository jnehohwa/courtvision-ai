from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceStatus(StrEnum):
    REPLAY = "replay"
    DELAYED = "delayed"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class TeamResponse(BaseModel):
    id: str
    name: str
    abbreviation: str


class PredictionResponse(BaseModel):
    game_id: str
    kind: str
    home_probability: float = Field(ge=0, le=1)
    away_probability: float = Field(ge=0, le=1)
    model_version: str
    predicted_at: datetime
    feature_timestamp: datetime
    confidence: str


class GameResponse(BaseModel):
    id: str
    scheduled_at: datetime
    home_team: TeamResponse
    away_team: TeamResponse
    home_score: int
    away_score: int
    period: int
    clock_seconds: int
    status: str
    source_status: SourceStatus
    last_ingested_at: datetime | None
    prediction: PredictionResponse | None = None


class GamesResponse(BaseModel):
    date: date
    games: list[GameResponse]


class TimelinePoint(BaseModel):
    sequence: int
    period: int
    clock_seconds: int
    home_probability: float = Field(ge=0, le=1)
    description: str
    event_type: str
    home_score: int
    away_score: int
    x: float | None = None
    y: float | None = None
    shot_value: int | None = None


class LiveSnapshotResponse(BaseModel):
    game: GameResponse
    timeline: list[TimelinePoint]
    latest_sequence: int
    source_label: str
    is_stale: bool
    freshness_seconds: int | None
    live_model_version: str
    snapshot_generated_at: datetime


class ShotAttemptRequest(BaseModel):
    x: float = Field(ge=-25, le=25)
    y: float = Field(ge=0, le=47)
    shot_value: int
    period: int = Field(ge=1, le=8)
    game_clock_seconds: int = Field(ge=0, le=720)
    score_differential: int = Field(ge=-80, le=80)

    @field_validator("shot_value")
    @classmethod
    def valid_shot_value(cls, value: int) -> int:
        if value not in {2, 3}:
            raise ValueError("shot_value must be 2 or 3")
        return value


class ShotQualityRequest(BaseModel):
    player_id: str
    attempts: list[ShotAttemptRequest] = Field(min_length=1, max_length=100)


class ShotQualityResult(BaseModel):
    x: float
    y: float
    distance_feet: float
    angle_degrees: float
    shot_value: int
    make_probability: float = Field(ge=0, le=1)
    expected_points: float = Field(ge=0, le=3)
    quality_label: str


class ShotQualityResponse(BaseModel):
    player_id: str
    definition: str
    model_version: str
    attempts: list[ShotQualityResult]


class PlayPayload(BaseModel):
    sequence: int
    source_event_id: str
    revision: int
    event_type: str
    description: str
    period: int
    clock_seconds: int
    home_score: int
    away_score: int
    possession_team_id: str | None
    home_fouls: int
    away_fouls: int
    x: float | None
    y: float | None
    shot_value: int | None
    home_probability: float


class WebSocketEnvelope(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    type: str
    schema_version: str = "1.0"
    game_id: str
    sequence: int = Field(ge=0)
    occurred_at: datetime
    ingested_at: datetime
    source_status: SourceStatus
    model_version: str | None
    payload: dict[str, object]


class SourceHealthResponse(BaseModel):
    status: str
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_event_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    total_polls: int
    total_events: int
    current_poll_interval_seconds: float | None
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    database: str
    redis: str
    latest_ingestion_at: datetime | None
    data_lag_seconds: int | None
    delayed_live_enabled: bool
    sources: dict[str, SourceHealthResponse]


class ReplayStartResponse(BaseModel):
    game_id: str
    status: str
    event_count: int
