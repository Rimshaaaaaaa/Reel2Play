"""A/B tests: one link that shares visitors between three versions of an ad (feature 19).

Revision ID: 0010_ab_tests
Revises: 0009_several_products
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_ab_tests"
down_revision: str | None = "0009_several_products"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("ads", sa.Column("ab_slug", sa.String(length=12), nullable=True))
    op.create_unique_constraint(op.f("uq_ads_ab_slug"), "ads", ["ab_slug"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("uq_ads_ab_slug"), "ads", type_="unique")
    op.drop_column("ads", "ab_slug")
