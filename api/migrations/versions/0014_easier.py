"""Self-improving loop: easier versions of games players find hard (feature 44).

Revision ID: 0014_easier
Revises: 0013_coupons
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_easier"
down_revision: str | None = "0013_coupons"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("ads", sa.Column("easier_for", sa.Uuid(), nullable=True))
    op.add_column("ads", sa.Column("suggestion", sa.String(length=10), nullable=True))
    op.create_index(op.f("ix_ads_easier_for"), "ads", ["easier_for"], unique=False)
    op.create_foreign_key(
        op.f("fk_ads_easier_for_ads"), "ads", "ads", ["easier_for"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("fk_ads_easier_for_ads"), "ads", type_="foreignkey")
    op.drop_index(op.f("ix_ads_easier_for"), table_name="ads")
    op.drop_column("ads", "suggestion")
    op.drop_column("ads", "easier_for")
