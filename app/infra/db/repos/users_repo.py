from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import TelegramUser


class UsersRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_user(
        self,
        *,
        telegram_id: int,
        username: str | None,
        display_name: str,
        language_code: str | None,
    ) -> TelegramUser:
        existing = await self.session.get(TelegramUser, telegram_id)
        if existing:
            existing.username = username
            existing.display_name = display_name
            existing.language_code = language_code
            await self.session.flush()
            return existing
        user = TelegramUser(
            telegram_id=telegram_id,
            username=username,
            display_name=display_name,
            language_code=language_code,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, telegram_id: int) -> TelegramUser | None:
        return await self.session.get(TelegramUser, telegram_id)

    async def find_by_username(self, username: str) -> TelegramUser | None:
        stmt = select(TelegramUser).where(TelegramUser.username == username.lstrip("@"))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
