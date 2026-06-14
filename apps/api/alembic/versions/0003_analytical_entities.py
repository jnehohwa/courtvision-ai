"""Add normalized analytical entities.

Revision ID: 0003
Revises: 0002
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_game_statistics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("team_id", sa.String(32), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("is_home", sa.Boolean(), nullable=False),
        sa.Column("offensive_rating", sa.Float(), nullable=False),
        sa.Column("defensive_rating", sa.Float(), nullable=False),
        sa.Column("pace", sa.Float(), nullable=False),
        sa.Column("rest_days", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("game_id", "team_id"),
    )
    op.create_index(
        "ix_team_game_statistics_game_id",
        "team_game_statistics",
        ["game_id"],
    )
    op.create_index(
        "ix_team_game_statistics_team_id",
        "team_game_statistics",
        ["team_id"],
    )
    op.create_index(
        "ix_team_game_statistics_team_as_of",
        "team_game_statistics",
        ["team_id", "as_of"],
    )

    op.create_table(
        "shots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("source_shot_id", sa.String(80), nullable=False),
        sa.Column("source_event_id", sa.String(80), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("player_id", sa.String(32), sa.ForeignKey("players.id"), nullable=True),
        sa.Column("team_id", sa.String(32), sa.ForeignKey("teams.id"), nullable=True),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("distance_feet", sa.Float(), nullable=False),
        sa.Column("angle_degrees", sa.Float(), nullable=False),
        sa.Column("shot_value", sa.Integer(), nullable=False),
        sa.Column("made", sa.Boolean(), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("game_clock_seconds", sa.Integer(), nullable=False),
        sa.Column("score_differential", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("game_id", "source_shot_id", "revision"),
    )
    op.create_index("ix_shots_game_id", "shots", ["game_id"])
    op.create_index("ix_shots_game_sequence", "shots", ["game_id", "sequence"])

    op.create_table(
        "feature_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("game_id", sa.String(64), sa.ForeignKey("games.id"), nullable=False),
        sa.Column("model_type", sa.String(40), nullable=False),
        sa.Column("feature_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prediction_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(20), nullable=False),
        sa.Column("dataset_version", sa.String(100), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.UniqueConstraint(
            "game_id",
            "model_type",
            "feature_timestamp",
            "schema_version",
        ),
    )
    op.create_index("ix_feature_snapshots_game_id", "feature_snapshots", ["game_id"])
    op.create_index(
        "ix_feature_snapshots_game_model",
        "feature_snapshots",
        ["game_id", "model_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_feature_snapshots_game_model", table_name="feature_snapshots")
    op.drop_index("ix_feature_snapshots_game_id", table_name="feature_snapshots")
    op.drop_table("feature_snapshots")
    op.drop_index("ix_shots_game_sequence", table_name="shots")
    op.drop_index("ix_shots_game_id", table_name="shots")
    op.drop_table("shots")
    op.drop_index(
        "ix_team_game_statistics_team_as_of",
        table_name="team_game_statistics",
    )
    op.drop_index(
        "ix_team_game_statistics_team_id",
        table_name="team_game_statistics",
    )
    op.drop_index(
        "ix_team_game_statistics_game_id",
        table_name="team_game_statistics",
    )
    op.drop_table("team_game_statistics")
