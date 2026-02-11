from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import orjson
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.domain.entities import CategoryBreakdown, ReportOutput, ReportPeriod, ReportTotals
from app.domain.value_objects import ReportPeriodKind
from app.infra.db.repos.families_repo import FamiliesRepo
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
                debug_meta=raw.get("debug_meta", {}),
            )

        sheet_id = await self._sheet_id_by_family(family_id)
        if not sheet_id:
            raise ValueError("Family sheet not found")
        rows = await self._sheets_gateway.read_expenses(sheet_id=sheet_id)
        filtered = self._filter_rows(rows=rows, period=period, tz=tz)

        total = Decimal("0")
        currency = ""
        by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_item: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_merchant: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        for row in filtered:
            row_total = Decimal(row.get("total_price", "0") or "0")
            total += row_total
            currency = row.get("currency", currency or self._settings.default_currency)
            category = row.get("category", "Другое")
            item = row.get("item_name", "N/A")
            merchant = row.get("merchant", "").strip() or "N/A"

            by_category[category] += row_total
            by_item[item] += row_total
            by_merchant[merchant] += row_total

        output = ReportOutput(
            totals=ReportTotals(
                total=total,
                currency=currency or self._settings.default_currency,
                expenses_count=len(filtered),
            ),
            by_category=sorted(
                [CategoryBreakdown(category=k, total=v) for k, v in by_category.items()],
                key=lambda x: x.total,
                reverse=True,
            ),
            top_items=sorted(by_item.items(), key=lambda x: x[1], reverse=True)[:5],
            top_merchants=sorted(by_merchant.items(), key=lambda x: x[1], reverse=True)[:5],
            debug_meta={"rows_total": len(rows), "rows_filtered": len(filtered)},
        )

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

    async def _sheet_id_by_family(self, family_id: UUID) -> str | None:
        async with self._session_factory() as session:
            family = await FamiliesRepo(session).get_by_family_id(family_id)
            await session.commit()
            return family.sheet_id if family else None

    @staticmethod
    def _filter_rows(
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
