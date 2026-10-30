"""Batch mode: several products uploaded together, one game each (feature 46).

Revision ID: 0015_batches
Revises: 0014_easier
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_batches"
down_revision: str | None = "0014_easier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("items", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_batches_shop_id_shops"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batches")),
    )
    op.create_index(op.f("ix_batches_shop_id"), "batches", ["shop_id"], unique=False)
    op.add_column("videos", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.add_column("videos", sa.Column("owner_product", sa.String(length=60), nullable=True))
    op.create_index(op.f("ix_videos_batch_id"), "videos", ["batch_id"], unique=False)
    op.create_foreign_key(
        op.f("fk_videos_batch_id_batches"),
        "videos",
        "batches",
        ["batch_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("fk_videos_batch_id_batches"), "videos", type_="foreignkey")
    op.drop_index(op.f("ix_videos_batch_id"), table_name="videos")
    op.drop_column("videos", "owner_product")
    op.drop_column("videos", "batch_id")
    op.drop_index(op.f("ix_batches_shop_id"), table_name="batches")
    op.drop_table("batches")
