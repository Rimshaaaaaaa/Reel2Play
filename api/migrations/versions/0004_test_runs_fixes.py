"""Play-test results, fix rounds, and the shop's report on each ad.

Revision ID: 0004_test_runs_fixes
Revises: 0003_builds
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_test_runs_fixes"
down_revision: str | None = "0003_builds"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "fixes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("failed_gates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("change", sa.Text(), nullable=False),
        sa.Column("build_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_fixes_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["build_id"], ["builds.id"], name=op.f("fk_fixes_build_id_builds"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fixes")),
    )
    op.create_index(op.f("ix_fixes_ad_id"), "fixes", ["ad_id"], unique=False)
    op.create_table(
        "test_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=False),
        sa.Column("build_id", sa.Uuid(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("gates", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("runs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("screenshots", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("critic", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["ad_id"], ["ads.id"], name=op.f("fk_test_runs_ad_id_ads"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["build_id"],
            ["builds.id"],
            name=op.f("fk_test_runs_build_id_builds"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_runs")),
    )
    op.create_index(op.f("ix_test_runs_ad_id"), "test_runs", ["ad_id"], unique=False)
    op.add_column(
        "ads", sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("ads", "report")
    op.drop_index(op.f("ix_test_runs_ad_id"), table_name="test_runs")
    op.drop_table("test_runs")
    op.drop_index(op.f("ix_fixes_ad_id"), table_name="fixes")
    op.drop_table("fixes")
