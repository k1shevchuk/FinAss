import orjson
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.google.sheets_gateway import GoogleSheetsGateway


class SettingsService:
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

    async def get_settings(self, actor_id: int) -> dict[str, str]:
        cache_key = f"sheet-settings:{actor_id}"
        cached = await self._redis.get(cache_key)
        if cached:
            return {str(k): str(v) for k, v in orjson.loads(cached).items()}
        sheet_id = await self._get_sheet_id(actor_id)
        if not sheet_id:
            return {}
        result = await self._sheets_gateway.get_settings(sheet_id=sheet_id)
        await self._redis.set(cache_key, orjson.dumps(result), ex=self._settings.cache_ttl_seconds)
        return result

    async def invalidate(self, actor_id: int) -> None:
        await self._redis.delete(f"sheet-settings:{actor_id}")

    async def set_setting(self, actor_id: int, key: str, value: str) -> None:
        sheet_id = await self._get_sheet_id(actor_id)
        if not sheet_id:
            raise ValueError("Family is not initialized. Use /start first.")
        await self._sheets_gateway.set_setting(sheet_id=sheet_id, key=key, value=value)
        await self.invalidate(actor_id)

    async def _get_sheet_id(self, actor_id: int) -> str | None:
        async with self._session_factory() as session:
            family = await FamiliesRepo(session).get_family_for_actor(actor_id)
            await session.commit()
            return family.sheet_id if family else None
