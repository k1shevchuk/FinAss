import orjson
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.domain.entities import CategoryRule
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.google.sheets_gateway import GoogleSheetsGateway


class CategoryService:
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

    async def list_categories(self, actor_id: int) -> list[CategoryRule]:
        cache_key = f"categories:{actor_id}"
        cached = await self._redis.get(cache_key)
        if cached:
            raw = orjson.loads(cached)
            return [
                CategoryRule(
                    category=item["category"], keywords=item["keywords"], enabled=item["enabled"]
                )
                for item in raw
            ]
        sheet_id = await self._get_sheet_id(actor_id)
        if not sheet_id:
            return []
        categories = await self._sheets_gateway.get_categories(sheet_id=sheet_id)
        await self._redis.set(
            cache_key,
            orjson.dumps(
                [
                    {"category": c.category, "keywords": c.keywords, "enabled": c.enabled}
                    for c in categories
                ]
            ),
            ex=self._settings.cache_ttl_seconds,
        )
        return categories

    async def invalidate(self, actor_id: int) -> None:
        await self._redis.delete(f"categories:{actor_id}")

    async def add_category(self, actor_id: int, category: str, keywords: list[str]) -> None:
        sheet_id = await self._get_sheet_id(actor_id)
        if not sheet_id:
            raise ValueError("Family is not initialized. Use /start first.")
        await self._sheets_gateway.add_category(
            sheet_id=sheet_id,
            category=category,
            keywords=keywords,
        )
        await self.invalidate(actor_id)

    async def set_category_enabled(self, actor_id: int, category: str, enabled: bool) -> bool:
        sheet_id = await self._get_sheet_id(actor_id)
        if not sheet_id:
            raise ValueError("Family is not initialized. Use /start first.")
        updated = await self._sheets_gateway.set_category_enabled(
            sheet_id=sheet_id,
            category=category,
            enabled=enabled,
        )
        await self.invalidate(actor_id)
        return updated

    async def _get_sheet_id(self, actor_id: int) -> str | None:
        async with self._session_factory() as session:
            family = await FamiliesRepo(session).get_family_for_actor(actor_id)
            await session.commit()
            return family.sheet_id if family else None
