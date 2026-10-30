"""Agency workspace with several brands and roles (feature 47).

Revision ID: 0019_agencies
Revises: 0018_leads
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_agencies"
down_revision: str | None = "0018_leads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agencies")),
    )
    op.create_table(
        "agency_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agency_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agency_id"],
            ["agencies.id"],
            name=op.f("fk_agency_members_agency_id_agencies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agency_members")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_agency_members_key_hash")),
    )
    op.create_index(
        op.f("ix_agency_members_agency_id"), "agency_members", ["agency_id"], unique=False
    )
    op.create_table(
        "agency_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agency_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["agency_id"],
            ["agencies.id"],
            name=op.f("fk_agency_invites_agency_id_agencies"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agency_invites")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_agency_invites_code_hash")),
    )
    op.create_index(
        op.f("ix_agency_invites_agency_id"), "agency_invites", ["agency_id"], unique=False
    )
    op.add_column("shops", sa.Column("agency_id", sa.Uuid(), nullable=True))
    op.create_index(op.f("ix_shops_agency_id"), "shops", ["agency_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_shops_agency_id_agencies"),
        "shops",
        "agencies",
        ["agency_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("fk_shops_agency_id_agencies"), "shops", type_="foreignkey")
    op.drop_index(op.f("ix_shops_agency_id"), table_name="shops")
    op.drop_column("shops", "agency_id")
    op.drop_index(op.f("ix_agency_invites_agency_id"), table_name="agency_invites")
    op.drop_table("agency_invites")
    op.drop_index(op.f("ix_agency_members_agency_id"), table_name="agency_members")
    op.drop_table("agency_members")
    op.drop_table("agencies")
