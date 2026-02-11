from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import Invite


class InvitesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_invite(
        self,
        *,
        family_id: UUID,
        code_hash: str,
        created_by_telegram_id: int,
        expires_at_utc: datetime,
        target_username: str | None,
        target_telegram_id: int | None,
    ) -> Invite:
        invite = Invite(
            family_id=family_id,
            code_hash=code_hash,
            created_by_telegram_id=created_by_telegram_id,
            target_username=target_username,
            target_telegram_id=target_telegram_id,
            expires_at_utc=expires_at_utc,
        )
        self.session.add(invite)
        await self.session.flush()
        return invite

    async def get_active_by_hash(self, *, code_hash: str, now_utc: datetime) -> Invite | None:
        stmt = select(Invite).where(
            and_(
                Invite.code_hash == code_hash,
                Invite.used_at_utc.is_(None),
                Invite.expires_at_utc > now_utc,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def use_invite(
        self, *, invite: Invite, used_by_telegram_id: int, used_at: datetime
    ) -> None:
        invite.used_by_telegram_id = used_by_telegram_id
        invite.used_at_utc = used_at
        await self.session.flush()
