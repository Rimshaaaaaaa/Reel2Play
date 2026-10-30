"""Several products from one video or a catalog of photos (feature 11).

Revision ID: 0009_several_products
Revises: 0008_voice
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_several_products"
down_revision: str | None = "0008_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "sprites", sa.Column("product_index", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "videos", sa.Column("catalog", sa.Boolean(), server_default=sa.false(), nullable=False)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("videos", "catalog")
    op.drop_column("sprites", "product_index")
