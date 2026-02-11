from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import AuditLog


class AuditRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        *,
        family_id: UUID,
        actor_telegram_id: int,
        action: str,
        details_safe_json: dict[str, Any],
    ) -> AuditLog:
        record = AuditLog(
            family_id=family_id,
            actor_telegram_id=actor_telegram_id,
            action=action,
            details_safe_json=details_safe_json,
        )
        self.session.add(record)
        await self.session.flush()
        return record
