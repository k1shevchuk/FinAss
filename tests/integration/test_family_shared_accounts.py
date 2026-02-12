from decimal import Decimal

import pytest

from app.domain.services.account_service import AccountService
from app.domain.services.audit_service import AuditService
from app.domain.services.family_service import FamilyService
from app.domain.services.onboarding_service import OnboardingService
from tests.integration.conftest import FakeQueue, FakeSheetsGateway, StubSettings


@pytest.mark.asyncio
async def test_family_shared_balances_owner_and_editor(session_factory) -> None:
    queue = FakeQueue()
    settings = StubSettings()
    sheets = FakeSheetsGateway()

    onboarding = OnboardingService(
        session_factory=session_factory,
        sheets_gateway=sheets,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
    )
    await onboarding.attach_existing_spreadsheet(
        telegram_id=100,
        username="owner100",
        display_name="Owner 100",
        language_code="ru",
        sheet_id="sheet-100",
    )

    audit = AuditService(session_factory=session_factory, queue=queue)  # type: ignore[arg-type]
    family_service = FamilyService(
        session_factory=session_factory,
        settings=settings,  # type: ignore[arg-type]
        audit_service=audit,
    )
    accounts = AccountService(
        session_factory=session_factory,
        queue=queue,  # type: ignore[arg-type]
        sheets_gateway=sheets,  # type: ignore[arg-type]
        audit_service=audit,
    )

    await accounts.initialize_balances(
        actor_id=100,
        actor_name="Owner 100",
        main_balance=Decimal("1000.00"),
        savings_balance=Decimal("300.00"),
    )

    invite = await family_service.create_invite(owner_id=100)
    await family_service.join_by_code(actor_id=200, code=invite.code)

    member_main, member_savings, currency = await accounts.get_balances(actor_id=200)
    assert member_main == Decimal("1000.00")
    assert member_savings == Decimal("300.00")
    assert currency == "RUB"

    with pytest.raises(PermissionError):
        await accounts.topup_main(
            actor_id=200,
            actor_name="Member 200",
            amount=Decimal("100.00"),
            note="editor should not topup",
        )

    new_main, new_savings, _ = await accounts.transfer_to_savings(
        actor_id=100,
        actor_name="Owner 100",
        amount=Decimal("200.00"),
        note="monthly savings",
    )
    assert new_main == Decimal("800.00")
    assert new_savings == Decimal("500.00")

    new_main, new_savings, _ = await accounts.spend_from_savings(
        actor_id=100,
        actor_name="Owner 100",
        amount=Decimal("120.00"),
        note="vacation prepay",
    )
    assert new_main == Decimal("800.00")
    assert new_savings == Decimal("380.00")

    member_main, member_savings, _ = await accounts.get_balances(actor_id=200)
    assert member_main == Decimal("800.00")
    assert member_savings == Decimal("380.00")

    names = [name for name, _ in queue.jobs]
    assert "append_ledger_job" in names
    assert "append_audit_job" in names


@pytest.mark.asyncio
async def test_family_invite_is_single_use(session_factory) -> None:
    queue = FakeQueue()
    settings = StubSettings()
    sheets = FakeSheetsGateway()

    onboarding = OnboardingService(
        session_factory=session_factory,
        sheets_gateway=sheets,  # type: ignore[arg-type]
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
    family = FamilyService(
        session_factory=session_factory,
        settings=settings,  # type: ignore[arg-type]
        audit_service=audit,
    )
    invite = await family.create_invite(owner_id=1)
    await family.join_by_code(actor_id=2, code=invite.code)
    with pytest.raises(ValueError):
        await family.join_by_code(actor_id=3, code=invite.code)


@pytest.mark.asyncio
async def test_family_invite_expired_immediately(session_factory) -> None:
    queue = FakeQueue()
    settings = StubSettings(invite_ttl_seconds=0)
    sheets = FakeSheetsGateway()

    onboarding = OnboardingService(
        session_factory=session_factory,
        sheets_gateway=sheets,  # type: ignore[arg-type]
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
    family = FamilyService(
        session_factory=session_factory,
        settings=settings,  # type: ignore[arg-type]
        audit_service=audit,
    )
    invite = await family.create_invite(owner_id=1)
    with pytest.raises(ValueError):
        await family.join_by_code(actor_id=2, code=invite.code)
