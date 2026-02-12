from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import ExpenseEntry


class ExpenseEntriesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_many(self, rows: list[ExpenseEntry]) -> None:
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
    ) -> list[ExpenseEntry]:
        stmt = (
            select(ExpenseEntry)
            .where(
                ExpenseEntry.family_id == family_id,
                ExpenseEntry.created_at_utc >= from_utc,
                ExpenseEntry.created_at_utc <= to_utc,
            )
            .order_by(ExpenseEntry.created_at_utc.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_family(self, *, family_id: UUID) -> int:
        stmt = select(func.count(ExpenseEntry.id)).where(ExpenseEntry.family_id == family_id)
        result = await self.session.execute(stmt)
        return int(result.scalar() or 0)

    async def list_by_family(self, *, family_id: UUID) -> list[ExpenseEntry]:
        stmt = (
            select(ExpenseEntry)
            .where(ExpenseEntry.family_id == family_id)
            .order_by(ExpenseEntry.created_at_utc.asc(), ExpenseEntry.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
