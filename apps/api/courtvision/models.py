from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from courtvision.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    abbreviation: Mapped[str] = mapped_column(String(8), unique=True)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    name: Mapped[str] = mapped_column(String(100))


class Game(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(80), unique=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    home_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    away_team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"))
    home_score: Mapped[int] = mapped_column(Integer, default=0)
    away_score: Mapped[int] = mapped_column(Integer, default=0)
    period: Mapped[int] = mapped_column(Integer, default=0)
    clock_seconds: Mapped[int] = mapped_column(Integer, default=2880)
    status: Mapped[str] = mapped_column(String(24), default="scheduled")
    source_status: Mapped[str] = mapped_column(String(24), default="replay")
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])


class TeamGameStatistic(Base):
    __tablename__ = "team_game_statistics"
    __table_args__ = (
        UniqueConstraint("game_id", "team_id"),
        Index("ix_team_game_statistics_team_as_of", "team_id", "as_of"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), index=True)
    is_home: Mapped[bool] = mapped_column(Boolean)
    offensive_rating: Mapped[float] = mapped_column(Float)
    defensive_rating: Mapped[float] = mapped_column(Float)
    pace: Mapped[float] = mapped_column(Float)
    rest_days: Mapped[int] = mapped_column(Integer)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(40))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_predictions_game_kind", "game_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    home_probability: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(40))
    feature_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    predicted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PlayByPlayEvent(Base):
    __tablename__ = "play_by_play_events"
    __table_args__ = (
        UniqueConstraint("game_id", "source_event_id", "revision"),
        UniqueConstraint("game_id", "sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    source_event_id: Mapped[str] = mapped_column(String(80))
    sequence: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    event_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(255))
    period: Mapped[int] = mapped_column(Integer)
    clock_seconds: Mapped[int] = mapped_column(Integer)
    home_score: Mapped[int] = mapped_column(Integer)
    away_score: Mapped[int] = mapped_column(Integer)
    possession_team_id: Mapped[str | None] = mapped_column(String(32))
    home_fouls: Mapped[int] = mapped_column(Integer, default=0)
    away_fouls: Mapped[int] = mapped_column(Integer, default=0)
    x: Mapped[float | None] = mapped_column(Float)
    y: Mapped[float | None] = mapped_column(Float)
    shot_value: Mapped[int | None] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Shot(Base):
    __tablename__ = "shots"
    __table_args__ = (
        UniqueConstraint("game_id", "source_shot_id", "revision"),
        Index("ix_shots_game_sequence", "game_id", "sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    source_shot_id: Mapped[str] = mapped_column(String(80))
    source_event_id: Mapped[str] = mapped_column(String(80))
    sequence: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    player_id: Mapped[str | None] = mapped_column(ForeignKey("players.id"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id"))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    distance_feet: Mapped[float] = mapped_column(Float)
    angle_degrees: Mapped[float] = mapped_column(Float)
    shot_value: Mapped[int] = mapped_column(Integer)
    made: Mapped[bool] = mapped_column(Boolean)
    period: Mapped[int] = mapped_column(Integer)
    game_clock_seconds: Mapped[int] = mapped_column(Integer)
    score_differential: Mapped[int] = mapped_column(Integer)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class FeatureSnapshot(Base):
    __tablename__ = "feature_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "model_type",
            "feature_timestamp",
            "schema_version",
        ),
        Index("ix_feature_snapshots_game_model", "game_id", "model_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.id"), index=True)
    model_type: Mapped[str] = mapped_column(String(40))
    feature_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    prediction_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    schema_version: Mapped[str] = mapped_column(String(20))
    dataset_version: Mapped[str] = mapped_column(String(100))
    features: Mapped[dict[str, Any]] = mapped_column(JSON)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint("model_type", "version"),
        Index(
            "uq_model_versions_active_type",
            "model_type",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active"),
        ),
        CheckConstraint(
            "is_active = (status = 'active')",
            name="ck_model_versions_active_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_type: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[str] = mapped_column(String(40))
    artifact_uri: Mapped[str | None] = mapped_column(String(255))
    artifact_sha256: Mapped[str | None] = mapped_column(String(64))
    calibration_uri: Mapped[str | None] = mapped_column(String(255))
    feature_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    dataset_version: Mapped[str] = mapped_column(String(100))
    training_commit: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="candidate")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    promotion_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ModelActivation(Base):
    __tablename__ = "model_activations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_type", "model_version"],
            ["model_versions.model_type", "model_versions.version"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["model_type", "previous_model_version"],
            ["model_versions.model_type", "model_versions.version"],
            ondelete="RESTRICT",
        ),
        Index("ix_model_activations_type_activated", "model_type", "activated_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_type: Mapped[str] = mapped_column(String(40), index=True)
    model_version: Mapped[str] = mapped_column(String(40))
    previous_model_version: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(24))
    reason: Mapped[str] = mapped_column(String(255))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    metrics_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class SourceHealthRecord(Base):
    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(24))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    total_polls: Mapped[int] = mapped_column(Integer, default=0)
    total_events: Mapped[int] = mapped_column(Integer, default=0)
    current_poll_interval_seconds: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
