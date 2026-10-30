"""Unique win codes and their redemption (feature 40).

Revision ID: 0013_coupons
Revises: 0012_event_sources
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_coupons"
down_revision: str | None = "0012_event_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "coupons",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=13), nullable=False),
        sa.Column("variant", sa.String(length=4), nullable=False),
        sa.Column("source", sa.String(length=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_coupons_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coupons")),
        sa.UniqueConstraint("code", name=op.f("uq_coupons_code")),
    )
    op.create_index(op.f("ix_coupons_ad_id"), "coupons", ["ad_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_coupons_ad_id"), table_name="coupons")
    op.drop_table("coupons")
