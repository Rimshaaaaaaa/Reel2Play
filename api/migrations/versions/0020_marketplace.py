"""Template marketplace for designers: submissions and their review (feature 49).

Revision ID: 0020_marketplace
Revises: 0019_agencies
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_marketplace"
down_revision: str | None = "0019_agencies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "template_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("designer_name", sa.String(length=80), nullable=False),
        sa.Column("designer_contact", sa.String(length=200), nullable=False),
        sa.Column("template_id", sa.String(length=30), nullable=True),
        sa.Column("status", sa.String(length=14), nullable=False),
        sa.Column("problems", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("files_key", sa.String(length=300), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_template_submissions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_template_submissions_token_hash")),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("template_submissions")
