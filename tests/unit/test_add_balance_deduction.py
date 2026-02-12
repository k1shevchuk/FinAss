from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.bot.handlers.add import _persist_manual_item


class _DummyState:
    def __init__(self) -> None:
        local_dt = datetime(2026, 2, 12, 10, 30, tzinfo=ZoneInfo("Europe/Moscow"))
        self.data: dict[str, object] = {
            "quantity": "2",
            "unit_price": "150.50",
            "currency": "RUB",
            "item_name": "Тестовый товар",
            "timezone": "Europe/Moscow",
            "category": "Продукты",
            "local_dt": local_dt.isoformat(),
            "added_count": 0,
            "added_total": "0",
        }
        self.state = None

    async def get_data(self) -> dict[str, object]:
        return dict(self.data)

    async def update_data(self, **kwargs: object) -> None:
        self.data.update(kwargs)

    async def set_state(self, value: object) -> None:
        self.state = value


class _DummyExpense:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def add_manual_expense(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


class _DummyAccounts:
    def __init__(self) -> None:
        self.main_calls: list[dict[str, object]] = []
        self.savings_calls: list[dict[str, object]] = []

    async def spend_main_for_expense(self, **kwargs: object):  # type: ignore[no-untyped-def]
        self.main_calls.append(kwargs)
        return Decimal("0"), Decimal("0"), "RUB"

    async def spend_from_savings(self, **kwargs: object):  # type: ignore[no-untyped-def]
        self.savings_calls.append(kwargs)
        return Decimal("0"), Decimal("0"), "RUB"


class _DummyServices:
    def __init__(self) -> None:
        self.expense = _DummyExpense()
        self.accounts = _DummyAccounts()


@pytest.mark.asyncio
async def test_persist_manual_item_deducts_main_by_default() -> None:
    state = _DummyState()
    services = _DummyServices()

    total, currency = await _persist_manual_item(
        state=state,  # type: ignore[arg-type]
        services=services,  # type: ignore[arg-type]
        actor_id=1,
        actor_name="Owner",
        deduct_from_savings=False,
    )

    assert total == Decimal("301.00")
    assert currency == "RUB"
    assert len(services.expense.calls) == 1
    assert len(services.accounts.main_calls) == 1
    assert len(services.accounts.savings_calls) == 0


@pytest.mark.asyncio
async def test_persist_manual_item_can_deduct_from_savings() -> None:
    state = _DummyState()
    services = _DummyServices()

    total, currency = await _persist_manual_item(
        state=state,  # type: ignore[arg-type]
        services=services,  # type: ignore[arg-type]
        actor_id=1,
        actor_name="Owner",
        deduct_from_savings=True,
    )

    assert total == Decimal("301.00")
    assert currency == "RUB"
    assert len(services.expense.calls) == 1
    assert len(services.accounts.main_calls) == 0
    assert len(services.accounts.savings_calls) == 1
