"""Voice briefs: the owner's voice note about the offer (feature 10).

Revision ID: 0008_voice
Revises: 0007_tracking
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_voice"
down_revision: str | None = "0007_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("videos", sa.Column("voice_original_key", sa.String(length=300), nullable=True))
    op.add_column("videos", sa.Column("voice_key", sa.String(length=300), nullable=True))
    op.add_column("videos", sa.Column("voice_seconds", sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    for column in ("voice_seconds", "voice_key", "voice_original_key"):
        op.drop_column("videos", column)
