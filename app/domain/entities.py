from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.value_objects import ExpenseSource, MembershipRole, ReportPeriodKind


@dataclass(slots=True, frozen=True)
class OwnerContext:
    telegram_id: int
    display_name: str
    family_id: UUID
    timezone: str
    currency: str
    google_share_email: str = ""


@dataclass(slots=True, frozen=True)
class SpreadsheetInfo:
    sheet_id: str
    sheet_url: str


@dataclass(slots=True, frozen=True)
class CategoryRule:
    category: str
    keywords: list[str]
    enabled: bool = True


@dataclass(slots=True, frozen=True)
class ExpenseItem:
    item_name: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal
    category: str
    merchant: str | None = None
    notes: str | None = None


@dataclass(slots=True, frozen=True)
class ExpenseBatch:
    actor_telegram_id: int
    actor_name: str
    owner_telegram_id: int
    family_id: UUID
    source: ExpenseSource
    local_datetime: datetime
    timezone: str
    currency: str
    receipt_hash: str | None
    items: list[ExpenseItem]


@dataclass(slots=True, frozen=True)
class ExpenseRow:
    values: list[str]


@dataclass(slots=True, frozen=True)
class AuditRow:
    values: list[str]


@dataclass(slots=True, frozen=True)
class AppendResult:
    updated_rows: int


@dataclass(slots=True, frozen=True)
class TelegramPhotoMeta:
    file_id: str
    file_unique_id: str
    file_size: int | None


@dataclass(slots=True, frozen=True)
class ActorContext:
    telegram_id: int
    display_name: str
    owner_telegram_id: int
    family_id: UUID
    timezone: str
    currency: str


@dataclass(slots=True, frozen=True)
class ReceiptRef:
    raw_payload: str
    total: Decimal | None = None
    purchased_at: datetime | None = None
    merchant: str | None = None
    currency: str | None = None


@dataclass(slots=True, frozen=True)
class ReceiptItem:
    name: str
    quantity: Decimal
    unit_price: Decimal
    total_price: Decimal
    category: str


@dataclass(slots=True, frozen=True)
class ReceiptProcessResult:
    payload_hash: str
    payload_preview: str
    receipt_ref: ReceiptRef
    items: list[ReceiptItem]
    fallback_required: bool


@dataclass(slots=True, frozen=True)
class InviteCode:
    code: str
    expires_at_utc: datetime


@dataclass(slots=True, frozen=True)
class JoinResult:
    family_id: UUID
    role: MembershipRole


@dataclass(slots=True, frozen=True)
class Membership:
    family_id: UUID
    owner_telegram_id: int
    role: MembershipRole


@dataclass(slots=True, frozen=True)
class ReportPeriod:
    kind: ReportPeriodKind
    from_utc: datetime
    to_utc: datetime


@dataclass(slots=True, frozen=True)
class ReportTotals:
    total: Decimal
    currency: str
    expenses_count: int


@dataclass(slots=True, frozen=True)
class CategoryBreakdown:
    category: str
    total: Decimal


@dataclass(slots=True, frozen=True)
class ReportOutput:
    totals: ReportTotals
    by_category: list[CategoryBreakdown]
    top_items: list[tuple[str, Decimal]]
    top_merchants: list[tuple[str, Decimal]]
    topup_main: Decimal = Decimal("0")
    net_change: Decimal = Decimal("0")
    transferred_to_savings: Decimal = Decimal("0")
    spent_from_savings: Decimal = Decimal("0")
    debug_meta: dict[str, Any] = field(default_factory=dict)
