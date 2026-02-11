from collections.abc import Awaitable, Callable
from uuid import UUID

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.entities import Membership
from app.domain.value_objects import MembershipRole
from app.infra.db.repos.families_repo import FamiliesRepo


class PrivateChatOnlyMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[object]],
        event: TelegramObject,
        data: dict,
    ) -> object:
        message: Message | None = None
        if isinstance(event, Message):
            message = event
        elif isinstance(event, CallbackQuery):
            message = event.message if isinstance(event.message, Message) else None

        if message and message.chat.type != "private":
            await message.answer("Для безопасности используйте бота только в личном чате.")
            return None
        return await handler(event, data)


class AuthzGuard:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def ensure_member(self, telegram_id: int, family_id: UUID) -> Membership:
        async with self._session_factory() as session:
            repo = FamiliesRepo(session)
            membership = await repo.get_membership(family_id=family_id, telegram_id=telegram_id)
            family = await repo.get_by_family_id(family_id)
            await session.commit()
            if not membership or not family:
                raise PermissionError("Not a family member.")
            return Membership(
                family_id=family.family_id,
                owner_telegram_id=family.owner_telegram_id,
                role=MembershipRole(membership.role),
            )

    async def ensure_owner(self, telegram_id: int, family_id: UUID) -> None:
        membership = await self.ensure_member(telegram_id=telegram_id, family_id=family_id)
        if membership.role != MembershipRole.OWNER:
            raise PermissionError("Owner role required.")
