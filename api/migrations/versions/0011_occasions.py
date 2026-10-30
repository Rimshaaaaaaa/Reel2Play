"""Seasonal themes: the occasion the owner picks for a game (feature 22).

Revision ID: 0011_occasions
Revises: 0010_ab_tests
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_occasions"
down_revision: str | None = "0010_ab_tests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("videos", sa.Column("owner_occasion", sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("videos", "owner_occasion")
