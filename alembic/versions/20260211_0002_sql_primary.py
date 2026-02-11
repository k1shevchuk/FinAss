"""sql primary storage for expenses and ledger

Revision ID: 20260211_0002
Revises: 20260211_0001
Create Date: 2026-02-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260211_0002"
down_revision: str | None = "20260211_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "families",
        sa.Column("main_balance", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "families",
        sa.Column(
            "savings_balance",
            sa.Numeric(14, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "families",
        sa.Column("balances_updated_at_utc", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "expense_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("expense_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("created_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_name", sa.String(length=255), nullable=False),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.family_id"), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("receipt_hash", sa.String(length=128), nullable=True),
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.String(length=1024), nullable=True),
    )
    op.create_index("ix_expense_entries_family_id", "expense_entries", ["family_id"])
    op.create_index(
        "ix_expense_entries_owner_telegram_id",
        "expense_entries",
        ["owner_telegram_id"],
    )
    op.create_index("ix_expense_entries_created_at_utc", "expense_entries", ["created_at_utc"])
    op.create_index(
        "ix_expense_entries_family_created",
        "expense_entries",
        ["family_id", "created_at_utc"],
    )
    op.create_index(
        "ix_expense_entries_receipt_hash",
        "expense_entries",
        ["receipt_hash"],
    )

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("local_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("family_id", sa.Uuid(), sa.ForeignKey("families.family_id"), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("note", sa.String(length=1024), nullable=True),
    )
    op.create_index("ix_ledger_entries_family_id", "ledger_entries", ["family_id"])
    op.create_index(
        "ix_ledger_entries_owner_telegram_id",
        "ledger_entries",
        ["owner_telegram_id"],
    )
    op.create_index("ix_ledger_entries_at_utc", "ledger_entries", ["at_utc"])
    op.create_index(
        "ix_ledger_entries_family_at",
        "ledger_entries",
        ["family_id", "at_utc"],
    )


def downgrade() -> None:
    op.drop_index("ix_ledger_entries_family_at", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_at_utc", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_owner_telegram_id", table_name="ledger_entries")
    op.drop_index("ix_ledger_entries_family_id", table_name="ledger_entries")
    op.drop_table("ledger_entries")

    op.drop_index("ix_expense_entries_receipt_hash", table_name="expense_entries")
    op.drop_index("ix_expense_entries_family_created", table_name="expense_entries")
    op.drop_index("ix_expense_entries_created_at_utc", table_name="expense_entries")
    op.drop_index("ix_expense_entries_owner_telegram_id", table_name="expense_entries")
    op.drop_index("ix_expense_entries_family_id", table_name="expense_entries")
    op.drop_table("expense_entries")

    op.drop_column("families", "balances_updated_at_utc")
    op.drop_column("families", "savings_balance")
    op.drop_column("families", "main_balance")
