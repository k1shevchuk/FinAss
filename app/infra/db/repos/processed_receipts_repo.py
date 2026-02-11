from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import ProcessedReceipt


class ProcessedReceiptsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def exists(self, *, owner_telegram_id: int, receipt_hash: str) -> bool:
        stmt = select(ProcessedReceipt.id).where(
            ProcessedReceipt.owner_telegram_id == owner_telegram_id,
            ProcessedReceipt.receipt_hash == receipt_hash,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_processed(
        self,
        *,
        family_id: UUID,
        owner_telegram_id: int,
        receipt_hash: str,
        event_local_datetime: str,
        total_price: Decimal,
        currency: str,
    ) -> ProcessedReceipt:
        row = ProcessedReceipt(
            family_id=family_id,
            owner_telegram_id=owner_telegram_id,
            receipt_hash=receipt_hash,
            event_local_datetime=event_local_datetime,
            total_price=float(total_price),
            currency=currency,
        )
        self.session.add(row)
        await self.session.flush()
        return row
