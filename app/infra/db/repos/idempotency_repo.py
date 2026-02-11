from datetime import datetime

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import IdempotencyKey


class IdempotencyRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def cleanup_expired(self, *, now_utc: datetime) -> None:
        stmt = delete(IdempotencyKey).where(IdempotencyKey.expires_at_utc < now_utc)
        await self.session.execute(stmt)

    async def exists(self, *, scope: str, actor_telegram_id: int, idempotency_key: str) -> bool:
        stmt = select(IdempotencyKey.id).where(
            and_(
                IdempotencyKey.scope == scope,
                IdempotencyKey.actor_telegram_id == actor_telegram_id,
                IdempotencyKey.idempotency_key == idempotency_key,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        *,
        scope: str,
        actor_telegram_id: int,
        idempotency_key: str,
        status: str,
        expires_at_utc: datetime,
    ) -> IdempotencyKey:
        row = IdempotencyKey(
            scope=scope,
            actor_telegram_id=actor_telegram_id,
            idempotency_key=idempotency_key,
            status=status,
            expires_at_utc=expires_at_utc,
        )
        self.session.add(row)
        await self.session.flush()
        return row
