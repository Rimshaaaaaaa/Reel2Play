"""Ads, director analyses and product sprites; sample key on videos.

Revision ID: 0002_ads_analyses_sprites
Revises: 0001_foundation
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_ads_analyses_sprites"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("step", sa.String(length=20), nullable=True),
        sa.Column("template", sa.String(length=30), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("variant", sa.String(length=4), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_ads_shop_id_shops"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name=op.f("fk_ads_video_id_videos"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ads")),
    )
    op.create_index(op.f("ix_ads_group_id"), "ads", ["group_id"], unique=False)
    op.create_index(op.f("ix_ads_status"), "ads", ["status"], unique=False)
    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("video_id", sa.Uuid(), nullable=False),
        sa.Column("reading", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("brief", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("candidates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_analyses_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_analyses_video_id_videos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
    )
    op.create_index(op.f("ix_analyses_ad_id"), "analyses", ["ad_id"], unique=False)
    op.create_table(
        "sprites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("source_frame_key", sa.String(length=300), nullable=False),
        sa.Column("mask_key", sa.String(length=300), nullable=False),
        sa.Column("sprite_key", sa.String(length=300), nullable=False),
        sa.Column("method", sa.String(length=12), nullable=False),
        sa.Column("quality", sa.String(length=8), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("area_fraction", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_sprites_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sprites")),
    )
    op.create_index(op.f("ix_sprites_ad_id"), "sprites", ["ad_id"], unique=False)
    op.add_column("videos", sa.Column("sample_key", sa.String(length=60), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("videos", "sample_key")
    op.drop_index(op.f("ix_sprites_ad_id"), table_name="sprites")
    op.drop_table("sprites")
    op.drop_index(op.f("ix_analyses_ad_id"), table_name="analyses")
    op.drop_table("analyses")
    op.drop_index(op.f("ix_ads_status"), table_name="ads")
    op.drop_index(op.f("ix_ads_group_id"), table_name="ads")
    op.drop_table("ads")
