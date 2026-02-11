"""initial schema

Revision ID: 20260211_0001
Revises:
Create Date: 2026-02-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260211_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_users",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "families",
        sa.Column("family_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_telegram_id",
            sa.BigInteger(),
            sa.ForeignKey("telegram_users.telegram_id"),
            nullable=False,
        ),
        sa.Column("sheet_id", sa.String(length=128), nullable=False),
        sa.Column("sheet_url", sa.String(length=1024), nullable=False),
        sa.Column("default_currency", sa.String(length=8), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("rounding_mode", sa.String(length=32), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_families_owner_telegram_id", "families", ["owner_telegram_id"])

    op.create_table(
        "family_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.family_id"), nullable=False),
        sa.Column(
            "telegram_id",
            sa.BigInteger(),
            sa.ForeignKey("telegram_users.telegram_id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("added_by_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("joined_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("family_id", "telegram_id", name="uq_family_member"),
    )
    op.create_index("ix_family_members_family_id", "family_members", ["family_id"])

    op.create_table(
        "invites",
        sa.Column("invite_id", sa.Uuid(), primary_key=True),
        sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.family_id"), nullable=False),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("created_by_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("target_username", sa.String(length=64), nullable=True),
        sa.Column("target_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_telegram_id", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint("family_id", "code_hash", name="uq_family_code_hash"),
    )
    op.create_index("ix_invites_family_id", "invites", ["family_id"])
    op.create_index("ix_invites_expires_at_utc", "invites", ["expires_at_utc"])

    op.create_table(
        "processed_receipts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.family_id"), nullable=False),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("receipt_hash", sa.String(length=128), nullable=False),
        sa.Column("event_local_datetime", sa.String(length=64), nullable=False),
        sa.Column("total_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_telegram_id", "receipt_hash", name="uq_owner_receipt_hash"),
    )
    op.create_index("ix_processed_receipts_family_id", "processed_receipts", ["family_id"])
    op.create_index(
        "ix_processed_receipts_owner_telegram_id",
        "processed_receipts",
        ["owner_telegram_id"],
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.family_id"), nullable=False),
        sa.Column("at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("details_safe_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_audit_log_family_id", "audit_log", ["family_id"])

    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "scope",
            "actor_telegram_id",
            "idempotency_key",
            name="uq_idempotency_scope",
        ),
    )
    op.create_index("ix_idempotency_expires_at_utc", "idempotency_keys", ["expires_at_utc"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_expires_at_utc", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_audit_log_family_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_processed_receipts_owner_telegram_id", table_name="processed_receipts")
    op.drop_index("ix_processed_receipts_family_id", table_name="processed_receipts")
    op.drop_table("processed_receipts")
    op.drop_index("ix_invites_expires_at_utc", table_name="invites")
    op.drop_index("ix_invites_family_id", table_name="invites")
    op.drop_table("invites")
    op.drop_index("ix_family_members_family_id", table_name="family_members")
    op.drop_table("family_members")
    op.drop_index("ix_families_owner_telegram_id", table_name="families")
    op.drop_table("families")
    op.drop_table("telegram_users")
