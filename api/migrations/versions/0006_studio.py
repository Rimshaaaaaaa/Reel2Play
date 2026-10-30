"""Anonymous game events, blind preference answers, studio keys and the gallery flag.

Revision ID: 0006_studio
Revises: 0005_publish_whatsapp
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_studio"
down_revision: str | None = "0005_publish_whatsapp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("variant", sa.String(length=4), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("seconds", sa.Float(), nullable=True),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_events_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
    )
    op.create_index(op.f("ix_events_ad_id"), "events", ["ad_id"], unique=False)
    op.create_table(
        "preferences",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("choice", sa.String(length=8), nullable=False),
        sa.Column("game_side", sa.String(length=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_preferences_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_preferences")),
    )
    op.create_index(op.f("ix_preferences_ad_id"), "preferences", ["ad_id"], unique=False)
    op.add_column(
        "ads",
        sa.Column("in_gallery", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("shops", sa.Column("access_key_hash", sa.String(length=64), nullable=True))
    op.create_unique_constraint(op.f("uq_shops_access_key_hash"), "shops", ["access_key_hash"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("uq_shops_access_key_hash"), "shops", type_="unique")
    op.drop_column("shops", "access_key_hash")
    op.drop_column("ads", "in_gallery")
    op.drop_index(op.f("ix_preferences_ad_id"), table_name="preferences")
    op.drop_table("preferences")
    op.drop_index(op.f("ix_events_ad_id"), table_name="events")
    op.drop_table("events")
