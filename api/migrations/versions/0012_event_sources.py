"""Where a play came from: an ordinary link, the counter poster or the shop's website
(features 36 and 37). Nothing about the player.

Revision ID: 0012_event_sources
Revises: 0011_occasions
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_event_sources"
down_revision: str | None = "0011_occasions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "events",
        sa.Column("source", sa.String(length=6), nullable=False, server_default="link"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("events", "source")
