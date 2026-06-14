"""Add transactional model registry metadata and activation history.

Revision ID: 0005
Revises: 0004
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("model_versions") as batch:
        batch.add_column(sa.Column("artifact_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("calibration_uri", sa.String(255), nullable=True))
        batch.add_column(
            sa.Column(
                "status",
                sa.String(24),
                nullable=False,
                server_default="candidate",
            )
        )
        batch.add_column(
            sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "promotion_metadata",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )

    op.execute(
        sa.text(
            "UPDATE model_versions "
            "SET status = CASE WHEN is_active THEN 'active' ELSE 'retired' END, "
            "registered_at = CURRENT_TIMESTAMP, "
            "activated_at = CASE WHEN is_active THEN CURRENT_TIMESTAMP ELSE NULL END"
        )
    )

    with op.batch_alter_table("model_versions") as batch:
        batch.alter_column("registered_at", nullable=False)
        batch.create_check_constraint(
            "ck_model_versions_active_status",
            "is_active = (status = 'active')",
        )

    op.create_index(
        "uq_model_versions_active_type",
        "model_versions",
        ["model_type"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active"),
    )
    op.create_table(
        "model_activations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_type", sa.String(40), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("previous_model_version", sa.String(40), nullable=True),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics_snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["model_type", "model_version"],
            ["model_versions.model_type", "model_versions.version"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["model_type", "previous_model_version"],
            ["model_versions.model_type", "model_versions.version"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_model_activations_type_activated",
        "model_activations",
        ["model_type", "activated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_activations_type_activated",
        table_name="model_activations",
    )
    op.drop_table("model_activations")
    op.drop_index("uq_model_versions_active_type", table_name="model_versions")
    with op.batch_alter_table("model_versions") as batch:
        batch.drop_constraint(
            "ck_model_versions_active_status",
            type_="check",
        )
        batch.drop_column("promotion_metadata")
        batch.drop_column("deactivated_at")
        batch.drop_column("activated_at")
        batch.drop_column("registered_at")
        batch.drop_column("status")
        batch.drop_column("calibration_uri")
        batch.drop_column("artifact_sha256")
