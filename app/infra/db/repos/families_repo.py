from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.db.models import Family, FamilyMember


class FamiliesRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_family(
        self,
        *,
        family_id: UUID | None,
        owner_telegram_id: int,
        sheet_id: str,
        sheet_url: str,
        default_currency: str,
        timezone: str,
        rounding_mode: str,
    ) -> Family:
        family = Family(
            family_id=family_id or uuid4(),
            owner_telegram_id=owner_telegram_id,
            sheet_id=sheet_id,
            sheet_url=sheet_url,
            default_currency=default_currency,
            timezone=timezone,
            rounding_mode=rounding_mode,
            main_balance=0.0,
            savings_balance=0.0,
        )
        self.session.add(family)
        await self.session.flush()
        owner_member = FamilyMember(
            family_id=family.family_id,
            telegram_id=owner_telegram_id,
            role="owner",
            added_by_telegram_id=owner_telegram_id,
            is_active=True,
        )
        self.session.add(owner_member)
        await self.session.flush()
        return family

    async def get_by_owner(self, owner_telegram_id: int) -> Family | None:
        stmt = select(Family).where(Family.owner_telegram_id == owner_telegram_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_family_id(self, family_id: UUID) -> Family | None:
        return await self.session.get(Family, family_id)

    async def get_membership(self, *, family_id: UUID, telegram_id: int) -> FamilyMember | None:
        stmt = select(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.telegram_id == telegram_id,
            FamilyMember.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_family_for_actor(self, telegram_id: int) -> Family | None:
        stmt = (
            select(Family)
            .join(FamilyMember, FamilyMember.family_id == Family.family_id)
            .where(FamilyMember.telegram_id == telegram_id, FamilyMember.is_active.is_(True))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_members(self, family_id: UUID) -> list[FamilyMember]:
        stmt = select(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.is_active.is_(True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_member(
        self,
        *,
        family_id: UUID,
        telegram_id: int,
        role: str,
        added_by_telegram_id: int,
    ) -> FamilyMember:
        member = await self.get_membership(family_id=family_id, telegram_id=telegram_id)
        if member:
            member.role = role
            member.is_active = True
            member.added_by_telegram_id = added_by_telegram_id
            await self.session.flush()
            return member
        created = FamilyMember(
            family_id=family_id,
            telegram_id=telegram_id,
            role=role,
            added_by_telegram_id=added_by_telegram_id,
            is_active=True,
        )
        self.session.add(created)
        await self.session.flush()
        return created

    async def remove_member(self, *, family_id: UUID, telegram_id: int) -> bool:
        member = await self.get_membership(family_id=family_id, telegram_id=telegram_id)
        if not member:
            return False
        member.is_active = False
        await self.session.flush()
        return True
