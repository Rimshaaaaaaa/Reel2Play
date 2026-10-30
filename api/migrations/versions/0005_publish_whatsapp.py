"""Published outputs, short links, captions, run replays and WhatsApp chats.

Revision ID: 0005_publish_whatsapp
Revises: 0004_test_runs_fixes
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_publish_whatsapp"
down_revision: str | None = "0004_test_runs_fixes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "whatsapp_chats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wa_id", sa.String(length=20), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("pending", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["shop_id"],
            ["shops.id"],
            name=op.f("fk_whatsapp_chats_shop_id_shops"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_chats")),
        sa.UniqueConstraint("wa_id", name=op.f("uq_whatsapp_chats_wa_id")),
    )
    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["whatsapp_chats.id"],
            name=op.f("fk_whatsapp_messages_chat_id_whatsapp_chats"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_whatsapp_messages")),
    )
    op.create_index(
        op.f("ix_whatsapp_messages_chat_id"), "whatsapp_messages", ["chat_id"], unique=False
    )
    op.create_table(
        "exports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("key", sa.String(length=300), nullable=False),
        sa.Column("public", sa.Boolean(), nullable=False),
        sa.Column("content_type", sa.String(length=60), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_exports_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exports")),
        sa.UniqueConstraint("ad_id", "kind", name=op.f("uq_exports_ad_id")),
    )
    op.create_index(op.f("ix_exports_ad_id"), "exports", ["ad_id"], unique=False)
    op.add_column("ads", sa.Column("slug", sa.String(length=12), nullable=True))
    op.add_column(
        "ads", sa.Column("captions", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.add_column("ads", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(op.f("uq_ads_slug"), "ads", ["slug"])
    op.add_column(
        "test_runs",
        sa.Column(
            "replays",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("videos", sa.Column("whatsapp_chat_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_videos_whatsapp_chat_id_whatsapp_chats"),
        "videos",
        "whatsapp_chats",
        ["whatsapp_chat_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        op.f("fk_videos_whatsapp_chat_id_whatsapp_chats"), "videos", type_="foreignkey"
    )
    op.drop_column("videos", "whatsapp_chat_id")
    op.drop_column("test_runs", "replays")
    op.drop_constraint(op.f("uq_ads_slug"), "ads", type_="unique")
    op.drop_column("ads", "published_at")
    op.drop_column("ads", "captions")
    op.drop_column("ads", "slug")
    op.drop_index(op.f("ix_exports_ad_id"), table_name="exports")
    op.drop_table("exports")
    op.drop_index(op.f("ix_whatsapp_messages_chat_id"), table_name="whatsapp_messages")
    op.drop_table("whatsapp_messages")
    op.drop_table("whatsapp_chats")
