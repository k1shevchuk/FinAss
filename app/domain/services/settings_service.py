from datetime import UTC, datetime

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

        async with self._session_factory() as session:
            family = await FamiliesRepo(session).get_family_for_actor(actor_id)
            await session.commit()
            if not family:
                return {}
            payload = {
                "currency": family.default_currency,
                "timezone": family.timezone,
                "rounding_mode": family.rounding_mode,
                "main_balance": str(family.main_balance),
                "savings_balance": str(family.savings_balance),
                "updated_at_utc": (
                    family.balances_updated_at_utc.isoformat()
                    if family.balances_updated_at_utc
                    else datetime.now(tz=UTC).isoformat()
                ),
            }
        await self._redis.set(cache_key, orjson.dumps(payload), ex=self._settings.cache_ttl_seconds)
        return payload

    async def invalidate(self, actor_id: int) -> None:
        await self._redis.delete(f"sheet-settings:{actor_id}")

    async def set_setting(self, actor_id: int, key: str, value: str) -> None:
        sheet_id: str | None = None
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(actor_id)
            if not family:
                raise ValueError("Family is not initialized. Use /start first.")
            sheet_id = family.sheet_id
            if key == "currency":
                family.default_currency = value
            elif key == "timezone":
                family.timezone = value
            elif key == "rounding_mode":
                family.rounding_mode = value
            await session.commit()
        if sheet_id:
            await self._sheets_gateway.set_setting(sheet_id=sheet_id, key=key, value=value)
        await self.invalidate(actor_id)
