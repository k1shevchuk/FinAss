import uuid
from datetime import UTC, datetime
from decimal import Decimal

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import get_logger

from app.domain.entities import ExpenseBatch, ExpenseItem
from app.domain.services.audit_service import AuditService
from app.domain.value_objects import ExpenseSource
from app.infra.db.models import ExpenseEntry
from app.infra.db.repos.expense_entries_repo import ExpenseEntriesRepo
from app.infra.db.repos.families_repo import FamiliesRepo

logger = get_logger(__name__)


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
        sheet_id: str
        rows: list[ExpenseEntry]
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(actor_telegram_id)
            if not family:
                raise ValueError("Семья не инициализирована. Нажмите «Старт» и подключите таблицу.")
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
            sheet_id = family.sheet_id
            rows = self._build_rows(batch=batch)
            await ExpenseEntriesRepo(session).add_many(rows)
            await session.commit()
        await self._enqueue_rows(sheet_id=sheet_id, rows=rows)
        await self._audit_service.log(
            family_id=batch.family_id,
            actor_telegram_id=batch.actor_telegram_id,
            action="expense.add.manual",
            details_safe_json={
                "items": len(batch.items),
                "total": f"{total:.2f}",
                "currency": currency,
            },
            sheet_id=sheet_id,
        )

    async def add_expense_batch(self, *, batch: ExpenseBatch, sheet_id: str) -> None:
        rows = self._build_rows(batch=batch)
        async with self._session_factory() as session:
            await ExpenseEntriesRepo(session).add_many(rows)
            await session.commit()
        await self._enqueue_rows(sheet_id=sheet_id, rows=rows)
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

    async def _enqueue_rows(self, *, sheet_id: str, rows: list[ExpenseEntry]) -> None:
        payload = [self._to_sheet_row(row) for row in rows]
        job = await self._queue.enqueue_job("append_expenses_job", sheet_id, payload)
        logger.info(
            "expense.enqueue.append_expenses",
            sheet_id=sheet_id,
            rows=len(payload),
            job_id=str(getattr(job, "job_id", "")),
        )

    def _build_rows(self, *, batch: ExpenseBatch) -> list[ExpenseEntry]:
        rows: list[ExpenseEntry] = []
        for item in batch.items:
            created_at_utc = datetime.now(tz=UTC)
            rows.append(
                ExpenseEntry(
                    expense_id=str(uuid.uuid4()),
                    created_at_utc=created_at_utc,
                    local_datetime=batch.local_datetime,
                    timezone=batch.timezone,
                    actor_telegram_id=batch.actor_telegram_id,
                    actor_name=batch.actor_name,
                    owner_telegram_id=batch.owner_telegram_id,
                    family_id=batch.family_id,
                    source=batch.source.value,
                    receipt_hash=batch.receipt_hash,
                    item_name=item.item_name,
                    quantity=float(item.quantity),
                    unit_price=float(item.unit_price),
                    total_price=float(item.total_price),
                    currency=batch.currency,
                    category=item.category,
                    merchant=item.merchant,
                    notes=item.notes,
                )
            )
        return rows

    @staticmethod
    def _to_sheet_row(row: ExpenseEntry) -> list[str]:
        return [
            row.expense_id,
            row.created_at_utc.isoformat(),
            row.local_datetime.isoformat(),
            row.timezone,
            str(row.actor_telegram_id),
            row.actor_name,
            str(row.owner_telegram_id),
            str(row.family_id),
            row.source,
            row.receipt_hash or "",
            row.item_name,
            f"{row.quantity}",
            f"{row.unit_price}",
            f"{row.total_price}",
            row.currency,
            row.category,
            row.merchant or "",
            row.notes or "",
        ]
