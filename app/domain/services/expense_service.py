import uuid
from datetime import UTC, datetime
from decimal import Decimal

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities import ExpenseBatch, ExpenseItem
from app.domain.services.audit_service import AuditService
from app.domain.value_objects import ExpenseSource
from app.infra.db.repos.families_repo import FamiliesRepo


class ExpenseService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        queue: ArqRedis,
        audit_service: AuditService,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._audit_service = audit_service

    async def add_manual_expense(
        self,
        *,
        actor_telegram_id: int,
        actor_name: str,
        item_name: str,
        quantity: Decimal,
        unit_price: Decimal,
        category: str,
        currency: str,
        timezone: str,
        merchant: str | None,
        notes: str | None,
        local_dt: datetime,
    ) -> None:
        total = quantity * unit_price
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(actor_telegram_id)
            if not family:
                raise ValueError("Family is not initialized. Use /start first.")
            batch = ExpenseBatch(
                actor_telegram_id=actor_telegram_id,
                actor_name=actor_name,
                owner_telegram_id=family.owner_telegram_id,
                family_id=family.family_id,
                source=ExpenseSource.MANUAL,
                local_datetime=local_dt,
                timezone=timezone,
                currency=currency,
                receipt_hash=None,
                items=[
                    ExpenseItem(
                        item_name=item_name,
                        quantity=quantity,
                        unit_price=unit_price,
                        total_price=total,
                        category=category,
                        merchant=merchant,
                        notes=notes,
                    )
                ],
            )
            await session.commit()
        await self._enqueue_batch(sheet_id=family.sheet_id, batch=batch)
        await self._audit_service.log(
            family_id=batch.family_id,
            actor_telegram_id=batch.actor_telegram_id,
            action="expense.add.manual",
            details_safe_json={
                "items": len(batch.items),
                "total": f"{total:.2f}",
                "currency": currency,
            },
            sheet_id=family.sheet_id,
        )

    async def add_expense_batch(self, *, batch: ExpenseBatch, sheet_id: str) -> None:
        await self._enqueue_batch(sheet_id=sheet_id, batch=batch)
        total = sum((i.total_price for i in batch.items), start=Decimal("0"))
        await self._audit_service.log(
            family_id=batch.family_id,
            actor_telegram_id=batch.actor_telegram_id,
            action=f"expense.add.{batch.source.value}",
            details_safe_json={
                "items": len(batch.items),
                "total": f"{total:.2f}",
                "currency": batch.currency,
                "receipt_hash": batch.receipt_hash,
            },
            sheet_id=sheet_id,
        )

    async def _enqueue_batch(self, *, sheet_id: str, batch: ExpenseBatch) -> None:
        rows = [self._to_row(item=item, batch=batch) for item in batch.items]
        await self._queue.enqueue_job("append_expenses_job", sheet_id, rows)

    @staticmethod
    def _to_row(*, item: ExpenseItem, batch: ExpenseBatch) -> list[str]:
        return [
            str(uuid.uuid4()),
            datetime.now(tz=UTC).isoformat(),
            batch.local_datetime.isoformat(),
            batch.timezone,
            str(batch.actor_telegram_id),
            batch.actor_name,
            str(batch.owner_telegram_id),
            str(batch.family_id),
            batch.source.value,
            batch.receipt_hash or "",
            item.item_name,
            f"{item.quantity}",
            f"{item.unit_price}",
            f"{item.total_price}",
            batch.currency,
            item.category,
            item.merchant or "",
            item.notes or "",
        ]
