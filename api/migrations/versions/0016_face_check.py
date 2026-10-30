"""Blur for bystanders' faces: whether each sprite's frame was checked (feature 55).

Revision ID: 0016_face_check
Revises: 0015_batches
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_face_check"
down_revision: str | None = "0015_batches"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "sprites",
        sa.Column("face_check", sa.String(length=10), nullable=False, server_default="unchecked"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("sprites", "face_check")
