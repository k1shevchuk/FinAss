from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities import ReportPeriod
from app.domain.services.report_service import ReportService
from app.domain.value_objects import ReportPeriodKind
from app.infra.db.models import ExpenseEntry, LedgerEntry


class DummyRedis:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    async def set(self, key: str, value: bytes, ex: int) -> None:
        _ = ex
        self.store[key] = value


class DummyGateway:
    async def read_expenses(self, *, sheet_id: str) -> list[dict[str, str]]:
        _ = sheet_id
        return []

    async def read_ledger(self, *, sheet_id: str) -> list[dict[str, str]]:
        _ = sheet_id
        return []


class DummySessionFactory:
    async def __aenter__(self) -> "DummySessionFactory":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        _ = (exc_type, exc, tb)

    def __call__(self):
        return self

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_report_filter_logic() -> None:
    service = ReportService(  # type: ignore[arg-type]
        session_factory=DummySessionFactory(),  # type: ignore[arg-type]
        redis=DummyRedis(),  # type: ignore[arg-type]
        sheets_gateway=DummyGateway(),  # type: ignore[arg-type]
        settings=type("S", (), {"report_cache_ttl_seconds": 120, "default_currency": "RUB"})(),
    )

    family_id = uuid4()
    now = datetime.now(tz=UTC)

    async def _load_sql_rows(*, family_id: object, period: ReportPeriod):  # type: ignore[no-untyped-def]
        _ = (family_id, period)
        return [
            ExpenseEntry(
                expense_id="exp-1",
                created_at_utc=now,
                local_datetime=now,
                timezone="UTC",
                actor_telegram_id=1,
                actor_name="u1",
                owner_telegram_id=1,
                family_id=uuid4(),
                source="manual",
                receipt_hash=None,
                item_name="Молоко",
                quantity=1,
                unit_price=100,
                total_price=100,
                currency="RUB",
                category="Продукты",
                merchant="Магнит",
                notes=None,
            ),
            ExpenseEntry(
                expense_id="exp-2",
                created_at_utc=now,
                local_datetime=now,
                timezone="UTC",
                actor_telegram_id=1,
                actor_name="u1",
                owner_telegram_id=1,
                family_id=uuid4(),
                source="manual",
                receipt_hash=None,
                item_name="Такси",
                quantity=1,
                unit_price=200,
                total_price=200,
                currency="RUB",
                category="Транспорт",
                merchant="Yandex Go",
                notes=None,
            ),
        ], [
            LedgerEntry(
                entry_id="led-1",
                at_utc=now,
                local_datetime=now,
                timezone="UTC",
                actor_telegram_id=1,
                owner_telegram_id=1,
                family_id=family_id,
                type="topup_main",
                amount=1000,
                currency="RUB",
                note=None,
            ),
            LedgerEntry(
                entry_id="led-2",
                at_utc=now,
                local_datetime=now,
                timezone="UTC",
                actor_telegram_id=1,
                owner_telegram_id=1,
                family_id=family_id,
                type="transfer_to_savings",
                amount=250,
                currency="RUB",
                note=None,
            ),
        ]

    service._load_sql_rows = _load_sql_rows  # type: ignore[assignment]
    period = ReportPeriod(
        kind=ReportPeriodKind.WEEK,
        from_utc=datetime.now(tz=UTC) - timedelta(days=1),
        to_utc=datetime.now(tz=UTC) + timedelta(days=1),
    )
    result = await service.generate(family_id, period, "UTC")
    assert result.totals.total == Decimal("300.00")
    assert result.totals.expenses_count == 2
    assert result.net_change == Decimal("750.00")
    assert result.transferred_to_savings == Decimal("250.00")
