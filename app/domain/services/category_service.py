import orjson
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.domain.entities import CategoryRule
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.google.sheets_gateway import GoogleSheetsGateway
from app.utils.category_dictionary import category_dictionary_version, load_default_category_rules


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
        cache_key = f"categories:{actor_id}:{category_dictionary_version()}"
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
        sheet_categories = await self._sheets_gateway.get_categories(sheet_id=sheet_id)
        categories = self._merge_default_and_sheet(sheet_categories=sheet_categories)
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
        keys: list[bytes] = []
        async for key in self._redis.scan_iter(match=f"categories:{actor_id}:*"):
            keys.append(key)
        if keys:
            await self._redis.delete(*keys)

    async def add_category(self, actor_id: int, category: str, keywords: list[str]) -> None:
        sheet_id = await self._get_sheet_id(actor_id)
        if not sheet_id:
            raise ValueError("Семья не инициализирована. Нажмите «Старт» и подключите таблицу.")
        await self._sheets_gateway.add_category(
            sheet_id=sheet_id,
            category=category,
            keywords=keywords,
        )
        await self.invalidate(actor_id)

    async def set_category_enabled(self, actor_id: int, category: str, enabled: bool) -> bool:
        sheet_id = await self._get_sheet_id(actor_id)
        if not sheet_id:
            raise ValueError("Семья не инициализирована. Нажмите «Старт» и подключите таблицу.")
        updated = await self._sheets_gateway.set_category_enabled(
            sheet_id=sheet_id,
            category=category,
            enabled=enabled,
        )
        await self.invalidate(actor_id)
        return updated

    async def sync_defaults_to_sheet(self, actor_id: int) -> int:
        sheet_id = await self._get_sheet_id(actor_id)
        if not sheet_id:
            raise ValueError("Семья не инициализирована. Нажмите «Старт» и подключите таблицу.")
        current = await self._sheets_gateway.get_categories(sheet_id=sheet_id)
        current_index = {item.category.casefold() for item in current}
        missing = [
            rule for rule in load_default_category_rules() if rule.category.casefold() not in current_index
        ]
        for rule in missing:
            await self._sheets_gateway.add_category(
                sheet_id=sheet_id,
                category=rule.category,
                keywords=rule.keywords,
            )
        await self.invalidate(actor_id)
        return len(missing)

    async def _get_sheet_id(self, actor_id: int) -> str | None:
        async with self._session_factory() as session:
            family = await FamiliesRepo(session).get_family_for_actor(actor_id)
            await session.commit()
            return family.sheet_id if family else None

    @staticmethod
    def _merge_default_and_sheet(*, sheet_categories: list[CategoryRule]) -> list[CategoryRule]:
        merged: dict[str, CategoryRule] = {}
        for rule in load_default_category_rules():
            merged[rule.category.casefold()] = CategoryRule(
                category=rule.category,
                keywords=list(rule.keywords),
                enabled=rule.enabled,
            )
        for rule in sheet_categories:
            key = rule.category.casefold()
            current = merged.get(key)
            if current is None:
                merged[key] = CategoryRule(
                    category=rule.category,
                    keywords=list(rule.keywords),
                    enabled=rule.enabled,
                )
                continue

            merged[key] = CategoryRule(
                category=rule.category or current.category,
                keywords=CategoryService._merge_keywords(current.keywords, rule.keywords),
                enabled=rule.enabled,
            )
        return list(merged.values())

    @staticmethod
    def _merge_keywords(base: list[str], extra: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for value in [*base, *extra]:
            token = str(value).strip()
            if not token:
                continue
            key = token.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
        return out
