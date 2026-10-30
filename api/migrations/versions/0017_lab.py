"""Custom mechanics: the owner asks for an experimental game (feature 24).

Revision ID: 0017_lab
Revises: 0016_face_check
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_lab"
down_revision: str | None = "0016_face_check"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "videos", sa.Column("lab", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("videos", "lab")
