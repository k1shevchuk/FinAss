import pytest

from app.domain.entities import CategoryRule
from app.domain.services.category_matcher_service import CategoryMatcherService


class DummyCategoryService:
    async def list_categories(self, actor_id: int) -> list[CategoryRule]:
        _ = actor_id
        return [
            CategoryRule(category="Продукты", keywords=["молоко", "сыр"], enabled=True),
            CategoryRule(category="Транспорт", keywords=["такси", "bus"], enabled=True),
        ]


@pytest.mark.asyncio
async def test_category_matcher_prefers_long_keyword() -> None:
    matcher = CategoryMatcherService(
        category_service=DummyCategoryService(),  # type: ignore[arg-type]
        cache_ttl_seconds=60,
    )
    category = await matcher.match(actor_id=1, text="Купил молоко и сыр в магазине")
    assert category == "Продукты"


@pytest.mark.asyncio
async def test_category_matcher_returns_none_on_empty_input() -> None:
    matcher = CategoryMatcherService(
        category_service=DummyCategoryService(),  # type: ignore[arg-type]
        cache_ttl_seconds=60,
    )
    category = await matcher.match(actor_id=1, text="   ")
    assert category is None
