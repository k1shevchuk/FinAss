from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.domain.services.audit_service import AuditService
from app.domain.services.expense_service import ExpenseService
from app.domain.services.onboarding_service import OnboardingService
from tests.integration.conftest import FakeQueue, FakeSheetsGateway, StubSettings


@pytest.mark.asyncio
async def test_add_manual_expense_enqueue(session_factory) -> None:
    queue = FakeQueue()
    settings = StubSettings()
    onboarding = OnboardingService(
        session_factory=session_factory,
        sheets_gateway=FakeSheetsGateway(),  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )
    await onboarding.attach_existing_spreadsheet(
        telegram_id=1,
        username="owner",
        display_name="Owner",
        language_code="ru",
        sheet_id="sheet-1",
    )
    audit = AuditService(session_factory=session_factory, queue=queue)  # type: ignore[arg-type]
    service = ExpenseService(session_factory=session_factory, queue=queue, audit_service=audit)  # type: ignore[arg-type]

    await service.add_manual_expense(
        actor_telegram_id=1,
        actor_name="Owner",
        item_name="Молоко",
        quantity=Decimal("2"),
        unit_price=Decimal("90"),
        category="Продукты",
        currency="RUB",
        timezone="Europe/Moscow",
        merchant="Магнит",
        notes="test",
        local_dt=datetime(2026, 2, 11, 19, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    names = [name for name, _ in queue.jobs]
    assert "append_expenses_job" in names
    assert "append_audit_job" in names
