from decimal import Decimal

import pytest

from app.bot.handlers.scan import (
    _deserialize_receipt_items,
    _format_items_preview,
    _normalize_receipt_items,
)
from app.domain.entities import ReceiptItem


def test_deserialize_receipt_items_ignores_invalid_payload() -> None:
    assert _deserialize_receipt_items(None) == []
    assert _deserialize_receipt_items({"bad": "shape"}) == []
    assert _deserialize_receipt_items([1, "abc", {"name": "", "total_price": "100"}]) == []


def test_deserialize_receipt_items_parses_valid_entries() -> None:
    raw = [
        {
            "name": "Молоко",
            "quantity": "2",
            "unit_price": "89.90",
            "total_price": "179.80",
            "category": "Продукты",
        },
        {
            "name": "Некорректная",
            "quantity": "abc",
            "unit_price": "12",
            "total_price": "24",
            "category": "Другое",
        },
    ]
    items = _deserialize_receipt_items(raw)
    assert len(items) == 1
    assert items[0].name == "Молоко"
    assert items[0].quantity == Decimal("2")
    assert items[0].total_price == Decimal("179.80")


def test_format_items_preview_limits_output() -> None:
    items = [
        ReceiptItem(
            name=f"Товар {i}",
            quantity=Decimal("1"),
            unit_price=Decimal("10"),
            total_price=Decimal("10"),
            category="Другое",
        )
        for i in range(1, 11)
    ]
    text = _format_items_preview(items, limit=3)
    assert "1. Товар 1" in text
    assert "... и еще 7 поз." in text


class _DummyMatcher:
    async def match(self, *, actor_id: int, text: str) -> str | None:
        _ = actor_id
        normalized = text.casefold()
        if "киви" in normalized or "томат" in normalized:
            return "Продукты"
        return None


class _DummyServices:
    def __init__(self) -> None:
        self.category_matcher = _DummyMatcher()


@pytest.mark.asyncio
async def test_normalize_receipt_items_replaces_other_with_match() -> None:
    items = [
        ReceiptItem(
            name="Киви фасованное 500г",
            quantity=Decimal("1"),
            unit_price=Decimal("119.99"),
            total_price=Decimal("119.99"),
            category="Другое",
        )
    ]
    normalized = await _normalize_receipt_items(
        items=items,
        categories=["Продукты", "Другое"],
        services=_DummyServices(),  # type: ignore[arg-type]
        actor_id=777,
    )
    assert len(normalized) == 1
    assert normalized[0].category == "Продукты"


@pytest.mark.asyncio
async def test_normalize_receipt_items_keeps_specific_category() -> None:
    items = [
        ReceiptItem(
            name="Киви фасованное 500г",
            quantity=Decimal("1"),
            unit_price=Decimal("119.99"),
            total_price=Decimal("119.99"),
            category="Фрукты",
        )
    ]
    normalized = await _normalize_receipt_items(
        items=items,
        categories=["Фрукты", "Продукты", "Другое"],
        services=_DummyServices(),  # type: ignore[arg-type]
        actor_id=777,
    )
    assert len(normalized) == 1
    assert normalized[0].category == "Фрукты"
