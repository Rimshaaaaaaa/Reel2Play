"""Foundation tables: shops, brand kits, videos, job queue, audit log, model calls.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor", sa.String(length=60), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("subject_type", sa.String(length=30), nullable=False),
        sa.Column("subject_id", sa.String(length=60), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        sa.UniqueConstraint("entry_hash", name=op.f("uq_audit_log_entry_hash")),
    )
    op.create_index(op.f("ix_audit_log_subject_id"), "audit_log", ["subject_id"], unique=False)
    op.create_index(op.f("ix_audit_log_subject_type"), "audit_log", ["subject_type"], unique=False)
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("kind", sa.String(length=60), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=80), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index(op.f("ix_jobs_kind"), "jobs", ["kind"], unique=False)
    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"], unique=False)
    op.create_table(
        "model_calls",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ad_id", sa.Uuid(), nullable=True),
        sa.Column("video_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("endpoint", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_name", sa.String(length=60), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("usd_cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("pkr_cost", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_calls")),
    )
    op.create_index(op.f("ix_model_calls_ad_id"), "model_calls", ["ad_id"], unique=False)
    op.create_index(op.f("ix_model_calls_video_id"), "model_calls", ["video_id"], unique=False)
    op.create_table(
        "shops",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("whatsapp_number", sa.String(length=20), nullable=True),
        sa.Column("shop_url", sa.String(length=500), nullable=True),
        sa.Column("brand_kit_id", sa.Uuid(), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shops")),
    )
    op.create_table(
        "brand_kits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("palette", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("logo_key", sa.String(length=300), nullable=True),
        sa.Column("fonts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tone", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_brand_kits_shop_id_shops"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_brand_kits")),
    )
    op.create_table(
        "videos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shop_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("original_key", sa.String(length=300), nullable=True),
        sa.Column("muted_key", sa.String(length=300), nullable=True),
        sa.Column("audio_key", sa.String(length=300), nullable=True),
        sa.Column("photo_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("rights_confirmed", sa.Boolean(), nullable=False),
        sa.Column("audio_removed", sa.Boolean(), nullable=False),
        sa.Column("owner_price", sa.String(length=40), nullable=True),
        sa.Column("owner_offer", sa.String(length=200), nullable=True),
        sa.Column("cta_kind", sa.String(length=10), nullable=False),
        sa.Column("cta_target", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["shop_id"], ["shops.id"], name=op.f("fk_videos_shop_id_shops"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_videos")),
    )
    op.create_foreign_key(
        op.f("fk_shops_brand_kit_id_brand_kits"),
        "shops",
        "brand_kits",
        ["brand_kit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_jobs_due", "jobs", ["status", "run_after"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_jobs_due", table_name="jobs")
    op.drop_constraint(op.f("fk_shops_brand_kit_id_brand_kits"), "shops", type_="foreignkey")
    op.drop_table("videos")
    op.drop_table("brand_kits")
    op.drop_table("shops")
    op.drop_index(op.f("ix_model_calls_video_id"), table_name="model_calls")
    op.drop_index(op.f("ix_model_calls_ad_id"), table_name="model_calls")
    op.drop_table("model_calls")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_kind"), table_name="jobs")
    op.drop_table("jobs")
    op.drop_index(op.f("ix_audit_log_subject_type"), table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_subject_id"), table_name="audit_log")
    op.drop_table("audit_log")
