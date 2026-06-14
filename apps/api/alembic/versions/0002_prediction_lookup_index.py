"""Add the prediction lookup index.

Revision ID: 0002
Revises: 0001
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_predictions_game_kind",
        "predictions",
        ["game_id", "kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_predictions_game_kind", table_name="predictions")
