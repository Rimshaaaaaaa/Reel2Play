"""Animated sprites: the product followed across a short clip (feature 7).

Revision ID: 0007_tracking
Revises: 0006_studio
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_tracking"
down_revision: str | None = "0006_studio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("sprites", sa.Column("track_key", sa.String(length=300), nullable=True))
    op.add_column(
        "sprites", sa.Column("track_frames", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("sprites", sa.Column("track_fps", sa.Float(), nullable=True))
    op.add_column("sprites", sa.Column("track_method", sa.String(length=16), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for column in ("track_method", "track_fps", "track_frames", "track_key"):
        op.drop_column("sprites", column)
