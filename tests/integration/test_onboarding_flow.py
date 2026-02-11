import pytest

from app.domain.services.onboarding_service import OnboardingService
from app.infra.db.repos.families_repo import FamiliesRepo
from tests.integration.conftest import FakeSheetsGateway, StubSettings


@pytest.mark.asyncio
async def test_onboarding_attaches_sheet_and_creates_family(session_factory) -> None:
    service = OnboardingService(
        session_factory=session_factory,
        sheets_gateway=FakeSheetsGateway(),  # type: ignore[arg-type]
        settings=StubSettings(),  # type: ignore[arg-type]
    )
    sheet_id, sheet_url = await service.attach_existing_spreadsheet(
        telegram_id=1001,
        username="user1001",
        display_name="User One",
        language_code="ru",
        sheet_id="sheet-1001",
    )
    assert sheet_id == "sheet-1001"
    assert "docs.google.com" in sheet_url

    async with session_factory() as session:
        family = await FamiliesRepo(session).get_family_for_actor(1001)
        await session.commit()
        assert family is not None
        assert family.sheet_id == sheet_id
