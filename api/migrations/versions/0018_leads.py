"""Opt-in lead capture over WhatsApp, with consent (feature 43).

Revision ID: 0018_leads
Revises: 0017_lab
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_leads"
down_revision: str | None = "0017_lab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "shops",
        sa.Column("leads_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("shops", sa.Column("lead_code", sa.String(length=12), nullable=True))
    op.create_unique_constraint(op.f("uq_shops_lead_code"), "shops", ["lead_code"])
    op.create_table(
        "leads",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["whatsapp_chats.id"],
            name=op.f("fk_leads_chat_id_whatsapp_chats"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_leads_shop_id_shops"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
        sa.UniqueConstraint("shop_id", "chat_id", name=op.f("uq_leads_shop_id")),
    )
    op.create_index(op.f("ix_leads_chat_id"), "leads", ["chat_id"], unique=False)
    op.create_index(op.f("ix_leads_shop_id"), "leads", ["shop_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_leads_shop_id"), table_name="leads")
    op.drop_index(op.f("ix_leads_chat_id"), table_name="leads")
    op.drop_table("leads")
    op.drop_constraint(op.f("uq_shops_lead_code"), "shops", type_="unique")
    op.drop_column("shops", "lead_code")
    op.drop_column("shops", "leads_enabled")
