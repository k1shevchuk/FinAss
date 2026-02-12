from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities import (
    ActorContext,
    ExpenseBatch,
    ExpenseItem,
    ReceiptItem,
    ReceiptProcessResult,
    TelegramPhotoMeta,
)
from app.domain.value_objects import ExpenseSource
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.db.repos.processed_receipts_repo import ProcessedReceiptsRepo
from app.infra.receipt.pipeline import ReceiptPipeline
from app.utils.idempotency import build_receipt_hash
from app.utils.timezone import now_utc, to_local


class ReceiptService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        pipeline: ReceiptPipeline,
    ) -> None:
        self._session_factory = session_factory
        self._pipeline = pipeline

    async def process_photo(
        self, *, actor_telegram_id: int, actor_name: str, file_meta: TelegramPhotoMeta
    ) -> ReceiptProcessResult:
        context = await self._actor_context(
            actor_telegram_id=actor_telegram_id, actor_name=actor_name
        )
        if not context:
            raise ValueError("Семья не инициализирована. Нажмите «Старт» и подключите таблицу.")
        return await self._pipeline.process_photo(file_meta=file_meta, actor=context)

    async def build_batch_from_fallback(
        self,
        *,
        actor_telegram_id: int,
        actor_name: str,
        payload: str,
        item_name: str,
        total: Decimal,
        category: str,
        currency: str | None = None,
        merchant: str | None = None,
        notes: str | None = None,
    ) -> ExpenseBatch:
        context = await self._actor_context(
            actor_telegram_id=actor_telegram_id, actor_name=actor_name
        )
        if not context:
            raise ValueError("Семья не инициализирована. Нажмите «Старт» и подключите таблицу.")
        local_dt = to_local(now_utc(), context.timezone)
        receipt_hash = build_receipt_hash(
            payload=payload,
            local_dt=local_dt,
            total=total,
            currency=(currency or context.currency),
        )
        await self._assert_not_processed(
            owner_telegram_id=context.owner_telegram_id,
            receipt_hash=receipt_hash,
        )
        return ExpenseBatch(
            actor_telegram_id=context.telegram_id,
            actor_name=context.display_name,
            owner_telegram_id=context.owner_telegram_id,
            family_id=context.family_id,
            source=ExpenseSource.RECEIPT,
            local_datetime=local_dt,
            timezone=context.timezone,
            currency=currency or context.currency,
            receipt_hash=receipt_hash,
            items=[
                ExpenseItem(
                    item_name=item_name,
                    quantity=Decimal("1"),
                    unit_price=total,
                    total_price=total,
                    category=category,
                    merchant=merchant,
                    notes=notes,
                ),
            ],
        )

    async def build_batch_from_items(
        self,
        *,
        actor_telegram_id: int,
        actor_name: str,
        payload: str,
        items: list[ReceiptItem],
        currency: str | None = None,
        merchant: str | None = None,
        notes: str | None = None,
    ) -> ExpenseBatch:
        context = await self._actor_context(
            actor_telegram_id=actor_telegram_id, actor_name=actor_name
        )
        if not context:
            raise ValueError("Семья не инициализирована. Нажмите «Старт» и подключите таблицу.")
        if not items:
            raise ValueError("В чеке нет позиций для сохранения.")

        local_dt = to_local(now_utc(), context.timezone)
        resolved_currency = currency or context.currency
        total = sum((item.total_price for item in items), start=Decimal("0"))
        receipt_hash = build_receipt_hash(
            payload=payload,
            local_dt=local_dt,
            total=total,
            currency=resolved_currency,
        )
        await self._assert_not_processed(
            owner_telegram_id=context.owner_telegram_id,
            receipt_hash=receipt_hash,
        )

        expense_items = [
            ExpenseItem(
                item_name=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                category=item.category,
                merchant=merchant,
                notes=notes,
            )
            for item in items
        ]

        return ExpenseBatch(
            actor_telegram_id=context.telegram_id,
            actor_name=context.display_name,
            owner_telegram_id=context.owner_telegram_id,
            family_id=context.family_id,
            source=ExpenseSource.RECEIPT,
            local_datetime=local_dt,
            timezone=context.timezone,
            currency=resolved_currency,
            receipt_hash=receipt_hash,
            items=expense_items,
        )

    async def mark_processed(
        self,
        *,
        actor_telegram_id: int,
        receipt_hash: str,
        event_local_datetime: datetime,
        total_price: Decimal,
        currency: str,
    ) -> None:
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(actor_telegram_id)
            if not family:
                raise ValueError("Семья не инициализирована. Нажмите «Старт» и подключите таблицу.")
            await ProcessedReceiptsRepo(session).mark_processed(
                family_id=family.family_id,
                owner_telegram_id=family.owner_telegram_id,
                receipt_hash=receipt_hash,
                event_local_datetime=event_local_datetime.isoformat(),
                total_price=total_price,
                currency=currency,
            )
            await session.commit()

    async def _actor_context(
        self, *, actor_telegram_id: int, actor_name: str
    ) -> ActorContext | None:
        async with self._session_factory() as session:
            family = await FamiliesRepo(session).get_family_for_actor(actor_telegram_id)
            await session.commit()
            if not family:
                return None
            return ActorContext(
                telegram_id=actor_telegram_id,
                display_name=actor_name,
                owner_telegram_id=family.owner_telegram_id,
                family_id=family.family_id,
                timezone=family.timezone,
                currency=family.default_currency,
            )

    async def _assert_not_processed(self, *, owner_telegram_id: int, receipt_hash: str) -> None:
        async with self._session_factory() as session:
            exists = await ProcessedReceiptsRepo(session).exists(
                owner_telegram_id=owner_telegram_id,
                receipt_hash=receipt_hash,
            )
            await session.commit()
            if exists:
                raise ValueError("Этот чек уже был обработан ранее.")
