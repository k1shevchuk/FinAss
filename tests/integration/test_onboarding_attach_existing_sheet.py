import pytest

from app.domain.services.onboarding_service import OnboardingService
from app.infra.db.repos.families_repo import FamiliesRepo
from tests.integration.conftest import FakeSheetsGateway, StubSettings


@pytest.mark.asyncio
async def test_onboarding_attach_existing_sheet(session_factory) -> None:
    service = OnboardingService(
        session_factory=session_factory,
        sheets_gateway=FakeSheetsGateway(),  # type: ignore[arg-type]
        settings=StubSettings(),  # type: ignore[arg-type]
    )
    existing_sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz_1234567890"
    sheet_id, sheet_url = await service.attach_existing_spreadsheet(
        telegram_id=2002,
        username="user2002",
        display_name="User Two",
        language_code="ru",
        sheet_id=existing_sheet_id,
    )
    assert sheet_id == existing_sheet_id
    assert existing_sheet_id in sheet_url

    async with session_factory() as session:
        family = await FamiliesRepo(session).get_family_for_actor(2002)
        await session.commit()
        assert family is not None
        assert family.sheet_id == existing_sheet_id
