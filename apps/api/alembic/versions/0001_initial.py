"""Initial CourtVision schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("abbreviation", sa.String(8), nullable=False, unique=True),
    )
    op.create_table(
        "players",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("team_id", sa.String(32), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
    )
    op.create_table(
        "games",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("source_id", sa.String(80), nullable=False, unique=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("home_team_id", sa.String(32), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("away_team_id", sa.String(32), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("away_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clock_seconds", sa.Integer(), nullable=False, server_default="2880"),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_status", sa.String(24), nullable=False),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_type", sa.String(40), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("artifact_uri", sa.String(255), nullable=True),
        sa.Column("feature_schema", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("training_commit", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("model_type", "version"),
    )
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("home_probability", sa.Float(), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("feature_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
    )
    op.create_table(
        "play_by_play_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("source_event_id", sa.String(80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("clock_seconds", sa.Integer(), nullable=False),
        sa.Column("home_score", sa.Integer(), nullable=False),
        sa.Column("away_score", sa.Integer(), nullable=False),
        sa.Column("possession_team_id", sa.String(32), nullable=True),
        sa.Column("home_fouls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("away_fouls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("x", sa.Float(), nullable=True),
        sa.Column("y", sa.Float(), nullable=True),
        sa.Column("shot_value", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("game_id", "source_event_id", "revision"),
        sa.UniqueConstraint("game_id", "sequence"),
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_seen", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("play_by_play_events")
    op.drop_table("predictions")
    op.drop_table("model_versions")
    op.drop_table("games")
    op.drop_table("players")
    op.drop_table("teams")
