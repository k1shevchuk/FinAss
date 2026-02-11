from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import LedgerEntry


class LedgerEntriesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_many(self, rows: list[LedgerEntry]) -> None:
        if not rows:
            return
        self.session.add_all(rows)
        await self.session.flush()

    async def list_by_period(
        self,
        *,
        family_id: UUID,
        from_utc: datetime,
        to_utc: datetime,
    ) -> list[LedgerEntry]:
        stmt = (
            select(LedgerEntry)
            .where(
                LedgerEntry.family_id == family_id,
                LedgerEntry.at_utc >= from_utc,
                LedgerEntry.at_utc <= to_utc,
            )
            .order_by(LedgerEntry.at_utc.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
