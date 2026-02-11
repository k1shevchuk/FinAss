from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.domain.entities import OwnerContext
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.db.repos.users_repo import UsersRepo
from app.infra.google.sheets_gateway import GoogleSheetsGateway
from app.infra.google.template_builder import DASHBOARD_VERSION


class OnboardingService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        sheets_gateway: GoogleSheetsGateway,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._sheets_gateway = sheets_gateway
        self._settings = settings

    async def attach_existing_spreadsheet(
        self,
        *,
        telegram_id: int,
        username: str | None,
        display_name: str,
        language_code: str | None,
        sheet_id: str,
    ) -> tuple[str, str]:
        async with self._session_factory() as session:
            users_repo = UsersRepo(session)
            families_repo = FamiliesRepo(session)
            await users_repo.upsert_user(
                telegram_id=telegram_id,
                username=username,
                display_name=display_name,
                language_code=language_code,
            )
            existing = await families_repo.get_family_for_actor(telegram_id)
            if existing:
                await session.commit()
                return existing.sheet_id, existing.sheet_url

            family_id = uuid4()
            owner = OwnerContext(
                telegram_id=telegram_id,
                display_name=display_name,
                family_id=family_id,
                timezone=self._settings.default_timezone,
                currency=self._settings.default_currency,
            )
            spreadsheet = await self._sheets_gateway.attach_existing_spreadsheet(
                sheet_id=sheet_id,
                owner=owner,
            )
            await families_repo.create_family(
                family_id=family_id,
                owner_telegram_id=telegram_id,
                sheet_id=spreadsheet.sheet_id,
                sheet_url=spreadsheet.sheet_url,
                default_currency=self._settings.default_currency,
                timezone=self._settings.default_timezone,
                rounding_mode=self._settings.default_rounding_mode,
            )
            await session.commit()
            return spreadsheet.sheet_id, spreadsheet.sheet_url

    async def upgrade_existing_sheet_if_needed(
        self,
        *,
        telegram_id: int,
        display_name: str,
    ) -> None:
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(telegram_id)
            await session.commit()
            if not family:
                return

        settings = await self._sheets_gateway.get_settings(sheet_id=family.sheet_id)
        if settings.get("dashboard_version") == DASHBOARD_VERSION:
            return

        owner = OwnerContext(
            telegram_id=family.owner_telegram_id,
            display_name=display_name,
            family_id=family.family_id,
            timezone=family.timezone,
            currency=family.default_currency,
        )
        await self._sheets_gateway.attach_existing_spreadsheet(
            sheet_id=family.sheet_id,
            owner=owner,
        )
