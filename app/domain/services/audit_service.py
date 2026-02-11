from datetime import UTC
from typing import Any
from uuid import UUID

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infra.db.repos.audit_repo import AuditRepo


class AuditService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        queue: ArqRedis,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue

    async def log(
        self,
        *,
        family_id: UUID,
        actor_telegram_id: int,
        action: str,
        details_safe_json: dict[str, Any],
        sheet_id: str,
    ) -> None:
        async with self._session_factory() as session:
            repo = AuditRepo(session)
            record = await repo.log(
                family_id=family_id,
                actor_telegram_id=actor_telegram_id,
                action=action,
                details_safe_json=details_safe_json,
            )
            await session.commit()

        await self._queue.enqueue_job(
            "append_audit_job",
            sheet_id,
            [
                [
                    record.at_utc.astimezone(UTC).isoformat(),
                    str(actor_telegram_id),
                    action,
                    str(details_safe_json),
                ]
            ],
        )
