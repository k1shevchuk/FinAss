from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    language_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    memberships: Mapped[list["FamilyMember"]] = relationship(back_populates="user")


class Family(Base):
    __tablename__ = "families"

    family_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False, index=True
    )
    sheet_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sheet_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    rounding_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    main_balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0.0)
    savings_balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0.0)
    balances_updated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    members: Mapped[list["FamilyMember"]] = relationship(back_populates="family")


class FamilyMember(Base):
    __tablename__ = "family_members"
    __table_args__ = (UniqueConstraint("family_id", "telegram_id", name="uq_family_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("families.family_id"), index=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("telegram_users.telegram_id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    added_by_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    joined_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    family: Mapped[Family] = relationship(back_populates="members")
    user: Mapped[TelegramUser] = relationship(back_populates="memberships")


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        UniqueConstraint("family_id", "code_hash", name="uq_family_code_hash"),
        Index("ix_invites_expires_at_utc", "expires_at_utc"),
    )

    invite_id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("families.family_id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class ProcessedReceipt(Base):
    __tablename__ = "processed_receipts"
    __table_args__ = (
        UniqueConstraint("owner_telegram_id", "receipt_hash", name="uq_owner_receipt_hash"),
        Index("ix_processed_receipts_family_id", "family_id"),
        Index("ix_processed_receipts_owner_telegram_id", "owner_telegram_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("families.family_id"), nullable=False)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    receipt_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    event_local_datetime: Mapped[str] = mapped_column(String(64), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_family_id", "family_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("families.family_id"), nullable=False)
    at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    details_safe_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "scope", "actor_telegram_id", "idempotency_key", name="uq_idempotency_scope"
        ),
        Index("ix_idempotency_expires_at_utc", "expires_at_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExpenseEntry(Base):
    __tablename__ = "expense_entries"
    __table_args__ = (
        Index("ix_expense_entries_family_id", "family_id"),
        Index("ix_expense_entries_owner_telegram_id", "owner_telegram_id"),
        Index("ix_expense_entries_created_at_utc", "created_at_utc"),
        Index("ix_expense_entries_family_created", "family_id", "created_at_utc"),
        Index("ix_expense_entries_receipt_hash", "receipt_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    expense_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    local_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("families.family_id"), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    receipt_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    item_name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total_price: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    category: Mapped[str] = mapped_column(String(128), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1024), nullable=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        Index("ix_ledger_entries_family_id", "family_id"),
        Index("ix_ledger_entries_owner_telegram_id", "owner_telegram_id"),
        Index("ix_ledger_entries_at_utc", "at_utc"),
        Index("ix_ledger_entries_family_at", "family_id", "at_utc"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True)
    at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    local_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    family_id: Mapped[UUID] = mapped_column(ForeignKey("families.family_id"), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1024), nullable=True)
