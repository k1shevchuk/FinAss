import pytest

from app.domain.services.audit_service import AuditService
from app.domain.services.family_service import FamilyService
from app.domain.services.onboarding_service import OnboardingService
from tests.integration.conftest import FakeQueue, FakeSheetsGateway, StubSettings


@pytest.mark.asyncio
async def test_family_invite_join_flow(session_factory) -> None:
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
    family = FamilyService(
        session_factory=session_factory,
        settings=settings,  # type: ignore[arg-type]
        audit_service=audit,
    )

    invite = await family.create_invite(owner_id=1, target_username="@member")
    assert invite.code

    join = await family.join_by_code(actor_id=2, code=invite.code)
    assert join.role.value == "editor"
    assert len(queue.jobs) >= 2
