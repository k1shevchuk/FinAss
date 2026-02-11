from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bot.middlewares.authz import AuthzGuard
from app.infra.db.models import Base, Family, FamilyMember, TelegramUser


@pytest.mark.asyncio
async def test_authz_guard_owner_check() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

    family_id = uuid4()
    async with session_factory() as session:
        session.add(TelegramUser(telegram_id=1, display_name="Owner"))
        session.add(TelegramUser(telegram_id=2, display_name="Editor"))
        session.add(
            Family(
                family_id=family_id,
                owner_telegram_id=1,
                sheet_id="sheet",
                sheet_url="url",
                default_currency="RUB",
                timezone="Europe/Moscow",
                rounding_mode="HALF_UP",
            )
        )
        session.add(
            FamilyMember(
                family_id=family_id,
                telegram_id=1,
                role="owner",
                added_by_telegram_id=1,
                is_active=True,
            )
        )
        session.add(
            FamilyMember(
                family_id=family_id,
                telegram_id=2,
                role="editor",
                added_by_telegram_id=1,
                is_active=True,
            )
        )
        await session.commit()

    guard = AuthzGuard(session_factory)
    member = await guard.ensure_member(telegram_id=2, family_id=family_id)
    assert member.role.value == "editor"

    await guard.ensure_owner(telegram_id=1, family_id=family_id)
    with pytest.raises(PermissionError):
        await guard.ensure_owner(telegram_id=2, family_id=family_id)

    await engine.dispose()
