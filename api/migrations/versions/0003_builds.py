"""Compiled games: one row per build of an ad.

Revision ID: 0003_builds
Revises: 0002_ads_analyses_sprites
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_builds"
down_revision: str | None = "0002_ads_analyses_sprites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "builds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("template", sa.String(length=30), nullable=False),
        sa.Column("proposal", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("html_key", sa.String(length=300), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_builds_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_builds")),
    )
    op.create_index(op.f("ix_builds_ad_id"), "builds", ["ad_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_builds_ad_id"), table_name="builds")
    op.drop_table("builds")
