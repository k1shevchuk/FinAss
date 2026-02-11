from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.db.repos.idempotency_repo import IdempotencyRepo
from app.utils.timezone import now_utc


class IdempotencyService:
    def __init__(self, *, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def check_and_lock(self, scope: str, actor_id: int, key: str, ttl_sec: int) -> bool:
        now = now_utc()
        async with self._session_factory() as session:
            repo = IdempotencyRepo(session)
            await repo.cleanup_expired(now_utc=now)
            exists = await repo.exists(scope=scope, actor_telegram_id=actor_id, idempotency_key=key)
            if exists:
                await session.commit()
                return False
            await repo.create(
                scope=scope,
                actor_telegram_id=actor_id,
                idempotency_key=key,
                status="locked",
                expires_at_utc=now + timedelta(seconds=ttl_sec),
            )
            await session.commit()
            return True
