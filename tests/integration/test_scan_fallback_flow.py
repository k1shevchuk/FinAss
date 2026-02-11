from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.domain.entities import ReceiptProcessResult, ReceiptRef, TelegramPhotoMeta
from app.domain.services.audit_service import AuditService
from app.domain.services.expense_service import ExpenseService
from app.domain.services.onboarding_service import OnboardingService
from app.domain.services.receipt_service import ReceiptService
from tests.integration.conftest import FakeQueue, FakeSheetsGateway, StubSettings


class FakePipeline:
    async def process_photo(self, file_meta, actor):  # type: ignore[no-untyped-def]
        _ = (file_meta, actor)
        return ReceiptProcessResult(
            payload_hash="hash",
            payload_preview="t=20260211...",
            receipt_ref=ReceiptRef(raw_payload="t=20260211T1910&s=100.00", total=Decimal("100.00")),
            items=[],
            fallback_required=True,
        )


@pytest.mark.asyncio
async def test_scan_fallback_duplicate_protection(session_factory) -> None:
    queue = FakeQueue()
    settings = StubSettings()
    onboarding = OnboardingService(
        session_factory=session_factory,
        sheets_gateway=FakeSheetsGateway(),  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )
    await onboarding.ensure_user_and_family(
        telegram_id=1,
        username="owner",
        display_name="Owner",
        language_code="ru",
        google_share_email="owner@gmail.com",
    )
    audit = AuditService(session_factory=session_factory, queue=queue)  # type: ignore[arg-type]
    expense = ExpenseService(session_factory=session_factory, queue=queue, audit_service=audit)  # type: ignore[arg-type]
    receipt = ReceiptService(session_factory=session_factory, pipeline=FakePipeline())  # type: ignore[arg-type]

    process_result = await receipt.process_photo(
        actor_telegram_id=1,
        actor_name="Owner",
        file_meta=TelegramPhotoMeta(file_id="1", file_unique_id="u1", file_size=123),
    )
    assert process_result.fallback_required

    batch = await receipt.build_batch_from_fallback(
        actor_telegram_id=1,
        actor_name="Owner",
        payload=process_result.receipt_ref.raw_payload,
        item_name="Чек",
        total=Decimal("100.00"),
        category="Продукты",
        currency="RUB",
    )
    await expense.add_expense_batch(batch=batch, sheet_id="sheet-1")
    await receipt.mark_processed(
        actor_telegram_id=1,
        receipt_hash=batch.receipt_hash or "",
        event_local_datetime=datetime.now(tz=ZoneInfo("Europe/Moscow")),
        total_price=Decimal("100.00"),
        currency="RUB",
    )

    with pytest.raises(ValueError):
        await receipt.build_batch_from_fallback(
            actor_telegram_id=1,
            actor_name="Owner",
            payload=process_result.receipt_ref.raw_payload,
            item_name="Чек",
            total=Decimal("100.00"),
            category="Продукты",
            currency="RUB",
        )
