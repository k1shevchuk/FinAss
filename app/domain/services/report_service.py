from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo

import orjson
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.domain.entities import CategoryBreakdown, ReportOutput, ReportPeriod, ReportTotals
from app.domain.value_objects import ReportPeriodKind
from app.infra.db.models import ExpenseEntry, LedgerEntry
from app.infra.db.repos.expense_entries_repo import ExpenseEntriesRepo
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.db.repos.ledger_entries_repo import LedgerEntriesRepo
from app.infra.google.sheets_gateway import GoogleSheetsGateway


class ReportService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        redis: Redis,
        sheets_gateway: GoogleSheetsGateway,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._sheets_gateway = sheets_gateway
        self._settings = settings

    async def generate(self, family_id: UUID, period: ReportPeriod, tz: str) -> ReportOutput:
        cache_key = f"report:{family_id}:{period.kind}:{period.from_utc.isoformat()}:{period.to_utc.isoformat()}"
        cached = await self._redis.get(cache_key)
        if cached:
            raw = orjson.loads(cached)
            return ReportOutput(
                totals=ReportTotals(
                    total=Decimal(raw["totals"]["total"]),
                    currency=raw["totals"]["currency"],
                    expenses_count=raw["totals"]["expenses_count"],
                ),
                by_category=[
                    CategoryBreakdown(category=x["category"], total=Decimal(x["total"]))
                    for x in raw["by_category"]
                ],
                top_items=[(x[0], Decimal(x[1])) for x in raw["top_items"]],
                top_merchants=[(x[0], Decimal(x[1])) for x in raw["top_merchants"]],
                topup_main=Decimal(str(raw.get("topup_main", "0"))),
                net_change=Decimal(str(raw.get("net_change", "0"))),
                transferred_to_savings=Decimal(str(raw.get("transferred_to_savings", "0"))),
                spent_from_savings=Decimal(str(raw.get("spent_from_savings", "0"))),
                debug_meta=raw.get("debug_meta", {}),
            )

        expenses, ledger = await self._load_sql_rows(family_id=family_id, period=period)
        data_source = "sql"

        # Backward compatibility: if DB history is empty, fallback to sheet projection.
        if not expenses and not ledger:
            sheet_id = await self._sheet_id_by_family(family_id)
            if sheet_id:
                sheet_expenses = await self._sheets_gateway.read_expenses(sheet_id=sheet_id)
                sheet_ledger = await self._sheets_gateway.read_ledger(sheet_id=sheet_id)
                expenses = self._sheet_to_expense_entries(
                    self._filter_sheet_rows(rows=sheet_expenses, period=period, tz=tz)
                )
                ledger = self._sheet_to_ledger_entries(
                    self._filter_sheet_ledger_rows(rows=sheet_ledger, period=period, tz=tz)
                )
                data_source = "sheets_fallback"

        output = self._aggregate(expenses=expenses, ledger=ledger)
        output.debug_meta["data_source"] = data_source
        output.debug_meta["rows_expenses"] = len(expenses)
        output.debug_meta["rows_ledger"] = len(ledger)

        await self._redis.set(
            cache_key,
            orjson.dumps(
                {
                    "totals": {
                        "total": str(output.totals.total),
                        "currency": output.totals.currency,
                        "expenses_count": output.totals.expenses_count,
                    },
                    "by_category": [
                        {"category": x.category, "total": str(x.total)} for x in output.by_category
                    ],
                    "top_items": [[x[0], str(x[1])] for x in output.top_items],
                    "top_merchants": [[x[0], str(x[1])] for x in output.top_merchants],
                    "topup_main": str(output.topup_main),
                    "net_change": str(output.net_change),
                    "transferred_to_savings": str(output.transferred_to_savings),
                    "spent_from_savings": str(output.spent_from_savings),
                    "debug_meta": output.debug_meta,
                }
            ),
            ex=self._settings.report_cache_ttl_seconds,
        )
        return output

    async def build_period(self, *, kind: ReportPeriodKind, tz: str) -> ReportPeriod:
        now_local = datetime.now(tz=ZoneInfo(tz))
        if kind == ReportPeriodKind.WEEK:
            start_local = (now_local - timedelta(days=now_local.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        elif kind == ReportPeriodKind.MONTH:
            start_local = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif kind == ReportPeriodKind.YEAR:
            start_local = now_local.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            raise ValueError("Use custom boundaries for custom period")
        return ReportPeriod(
            kind=kind,
            from_utc=start_local.astimezone(UTC),
            to_utc=now_local.astimezone(UTC),
        )

    async def _load_sql_rows(
        self, *, family_id: UUID, period: ReportPeriod
    ) -> tuple[list[ExpenseEntry], list[LedgerEntry]]:
        async with self._session_factory() as session:
            expenses_repo = ExpenseEntriesRepo(session)
            ledger_repo = LedgerEntriesRepo(session)
            expenses = await expenses_repo.list_by_period(
                family_id=family_id,
                from_utc=period.from_utc,
                to_utc=period.to_utc,
            )
            ledger = await ledger_repo.list_by_period(
                family_id=family_id,
                from_utc=period.from_utc,
                to_utc=period.to_utc,
            )
            await session.commit()
            return expenses, ledger

    async def _sheet_id_by_family(self, family_id: UUID) -> str | None:
        async with self._session_factory() as session:
            family = await FamiliesRepo(session).get_by_family_id(family_id)
            await session.commit()
            return family.sheet_id if family else None

    def _aggregate(
        self, *, expenses: list[ExpenseEntry], ledger: list[LedgerEntry]
    ) -> ReportOutput:
        total = Decimal("0")
        currency = self._settings.default_currency
        by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_item: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_merchant: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        for expense_row in expenses:
            row_total = Decimal(str(expense_row.total_price or "0"))
            total += row_total
            if expense_row.currency:
                currency = expense_row.currency
            category = expense_row.category or "Другое"
            item = expense_row.item_name or "N/A"
            merchant = (expense_row.merchant or "").strip() or "N/A"

            by_category[category] += row_total
            by_item[item] += row_total
            by_merchant[merchant] += row_total

        topup_main = Decimal("0")
        net_change = Decimal("0")
        transferred_to_savings = Decimal("0")
        spent_from_savings = Decimal("0")
        for ledger_row in ledger:
            entry_type = str(ledger_row.type).strip()
            try:
                amount = Decimal(str(ledger_row.amount or "0"))
            except (InvalidOperation, ValueError):
                continue
            if entry_type == "topup_main":
                topup_main += amount
                net_change += amount
            elif entry_type == "transfer_to_savings":
                net_change -= amount
                transferred_to_savings += amount
            elif entry_type == "spend_from_savings":
                spent_from_savings += amount

        return ReportOutput(
            totals=ReportTotals(
                total=total,
                currency=currency,
                expenses_count=len(expenses),
            ),
            by_category=sorted(
                [CategoryBreakdown(category=k, total=v) for k, v in by_category.items()],
                key=lambda x: x.total,
                reverse=True,
            ),
            top_items=sorted(by_item.items(), key=lambda x: x[1], reverse=True)[:5],
            top_merchants=sorted(by_merchant.items(), key=lambda x: x[1], reverse=True)[:5],
            topup_main=topup_main,
            net_change=net_change,
            transferred_to_savings=transferred_to_savings,
            spent_from_savings=spent_from_savings,
            debug_meta={},
        )

    @staticmethod
    def _filter_sheet_rows(
        rows: list[dict[str, str]], period: ReportPeriod, tz: str
    ) -> list[dict[str, str]]:
        local_tz = ZoneInfo(tz)
        out: list[dict[str, str]] = []
        for row in rows:
            created_raw = row.get("created_at_utc", "")
            if not created_raw:
                continue
            try:
                created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            created_local = created_at.astimezone(local_tz)
            if period.from_utc <= created_local.astimezone(UTC) <= period.to_utc:
                out.append(row)
        return out

    @staticmethod
    def _filter_sheet_ledger_rows(
        rows: list[dict[str, str]], period: ReportPeriod, tz: str
    ) -> list[dict[str, str]]:
        local_tz = ZoneInfo(tz)
        out: list[dict[str, str]] = []
        for row in rows:
            created_raw = row.get("at_utc", "")
            if not created_raw:
                continue
            try:
                created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=UTC)
            created_local = created_at.astimezone(local_tz)
            if period.from_utc <= created_local.astimezone(UTC) <= period.to_utc:
                out.append(row)
        return out

    @staticmethod
    def _sheet_to_expense_entries(rows: list[dict[str, str]]) -> list[ExpenseEntry]:
        out: list[ExpenseEntry] = []
        for row in rows:
            try:
                created_at = datetime.fromisoformat(
                    str(row.get("created_at_utc", "")).replace("Z", "+00:00")
                )
                local_dt = datetime.fromisoformat(
                    str(row.get("local_datetime", created_at.isoformat())).replace("Z", "+00:00")
                )
            except ValueError:
                continue
            family_raw = str(row.get("family_id", "")).strip()
            if family_raw:
                try:
                    family_id = UUID(family_raw)
                except ValueError:
                    family_id = UUID("00000000-0000-0000-0000-000000000000")
            else:
                family_id = UUID("00000000-0000-0000-0000-000000000000")
            out.append(
                ExpenseEntry(
                    expense_id=str(row.get("expense_id", "")),
                    created_at_utc=created_at,
                    local_datetime=local_dt,
                    timezone=str(row.get("timezone", "UTC")),
                    actor_telegram_id=int(str(row.get("actor_telegram_id", "0") or "0")),
                    actor_name=str(row.get("actor_name", "")),
                    owner_telegram_id=int(str(row.get("owner_telegram_id", "0") or "0")),
                    family_id=family_id,
                    source=str(row.get("source", "manual")),
                    receipt_hash=str(row.get("receipt_hash", "")) or None,
                    item_name=str(row.get("item_name", "")),
                    quantity=float(str(row.get("quantity", "0") or "0")),
                    unit_price=float(str(row.get("unit_price", "0") or "0")),
                    total_price=float(str(row.get("total_price", "0") or "0")),
                    currency=str(row.get("currency", "RUB")),
                    category=str(row.get("category", "Другое")),
                    merchant=str(row.get("merchant", "")) or None,
                    notes=str(row.get("notes", "")) or None,
                )
            )
        return out

    @staticmethod
    def _sheet_to_ledger_entries(rows: list[dict[str, str]]) -> list[LedgerEntry]:
        out: list[LedgerEntry] = []
        for row in rows:
            try:
                at_utc = datetime.fromisoformat(str(row.get("at_utc", "")).replace("Z", "+00:00"))
                local_dt = datetime.fromisoformat(
                    str(row.get("local_datetime", at_utc.isoformat())).replace("Z", "+00:00")
                )
            except ValueError:
                continue

            family_raw = str(row.get("family_id", "")).strip()
            if family_raw:
                family_id = UUID(family_raw)
            else:
                family_id = UUID("00000000-0000-0000-0000-000000000000")

            out.append(
                LedgerEntry(
                    entry_id=str(row.get("entry_id", "")),
                    at_utc=at_utc,
                    local_datetime=local_dt,
                    timezone=str(row.get("timezone", "UTC")),
                    actor_telegram_id=int(str(row.get("actor_telegram_id", "0") or "0")),
                    owner_telegram_id=int(str(row.get("owner_telegram_id", "0") or "0")),
                    family_id=family_id,
                    type=str(row.get("type", "")),
                    amount=float(str(row.get("amount", "0") or "0")),
                    currency=str(row.get("currency", "RUB")),
                    note=str(row.get("note", "")) or None,
                )
            )
        return out
