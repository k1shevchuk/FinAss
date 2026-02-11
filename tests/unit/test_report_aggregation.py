from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.entities import ReportPeriod
from app.domain.services.report_service import ReportService
from app.domain.value_objects import ReportPeriodKind


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
        now = datetime.now(tz=UTC)
        return [
            {
                "created_at_utc": now.isoformat(),
                "total_price": "100.00",
                "currency": "RUB",
                "category": "Продукты",
                "item_name": "Молоко",
                "merchant": "Магнит",
            },
            {
                "created_at_utc": now.isoformat(),
                "total_price": "200.00",
                "currency": "RUB",
                "category": "Транспорт",
                "item_name": "Такси",
                "merchant": "Yandex Go",
            },
        ]


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
    async def _sheet_id_by_family(_: object) -> str:
        return "sheet"

    service._sheet_id_by_family = _sheet_id_by_family  # type: ignore[assignment]
    period = ReportPeriod(
        kind=ReportPeriodKind.WEEK,
        from_utc=datetime.now(tz=UTC) - timedelta(days=1),
        to_utc=datetime.now(tz=UTC) + timedelta(days=1),
    )
    result = await service.generate(uuid4(), period, "UTC")
    assert result.totals.total == Decimal("300.00")
    assert result.totals.expenses_count == 2
