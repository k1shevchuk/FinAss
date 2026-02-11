from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.value_objects import MembershipRole
from app.infra.db.models import (
    AuditLog,
    ExpenseEntry,
    Family,
    FamilyMember,
    IdempotencyKey,
    Invite,
    LedgerEntry,
    ProcessedReceipt,
    TelegramUser,
)
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.google.sheets_gateway import GoogleSheetsGateway


@dataclass(slots=True, frozen=True)
class ResetResult:
    mode: str
    family_id: UUID | None
    sheet_id: str | None


class ResetService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        sheets_gateway: GoogleSheetsGateway,
    ) -> None:
        self._session_factory = session_factory
        self._sheets_gateway = sheets_gateway

    async def reset_user(self, *, actor_id: int) -> ResetResult:
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(actor_id)
            if not family:
                await self._delete_actor_local_only(session=session, actor_id=actor_id)
                await session.commit()
                return ResetResult(mode="local_only", family_id=None, sheet_id=None)

            membership = await families_repo.get_membership(
                family_id=family.family_id,
                telegram_id=actor_id,
            )
            if not membership:
                await self._delete_actor_local_only(session=session, actor_id=actor_id)
                await session.commit()
                return ResetResult(mode="local_only", family_id=None, sheet_id=None)

            role = MembershipRole(membership.role)
            if role == MembershipRole.OWNER:
                member_ids_stmt = select(FamilyMember.telegram_id).where(
                    FamilyMember.family_id == family.family_id
                )
                member_ids = [
                    int(item[0]) for item in (await session.execute(member_ids_stmt)).all()
                ]

                await session.execute(delete(Invite).where(Invite.family_id == family.family_id))
                await session.execute(
                    delete(ProcessedReceipt).where(ProcessedReceipt.family_id == family.family_id)
                )
                await session.execute(
                    delete(ExpenseEntry).where(ExpenseEntry.family_id == family.family_id)
                )
                await session.execute(
                    delete(LedgerEntry).where(LedgerEntry.family_id == family.family_id)
                )
                await session.execute(
                    delete(AuditLog).where(AuditLog.family_id == family.family_id)
                )
                if member_ids:
                    await session.execute(
                        delete(IdempotencyKey).where(
                            IdempotencyKey.actor_telegram_id.in_(member_ids)
                        )
                    )
                await session.execute(
                    delete(FamilyMember).where(FamilyMember.family_id == family.family_id)
                )
                await session.execute(delete(Family).where(Family.family_id == family.family_id))
                await session.execute(
                    delete(TelegramUser).where(TelegramUser.telegram_id == actor_id)
                )
                await session.commit()

                await self._sheets_gateway.wipe_family_data(sheet_id=family.sheet_id)
                return ResetResult(
                    mode="owner_wipe",
                    family_id=family.family_id,
                    sheet_id=family.sheet_id,
                )

            await session.execute(
                delete(FamilyMember).where(
                    FamilyMember.family_id == family.family_id,
                    FamilyMember.telegram_id == actor_id,
                )
            )
            await self._delete_actor_local_only(session=session, actor_id=actor_id)
            await session.commit()

        await self._sheets_gateway.purge_actor_data(
            sheet_id=family.sheet_id,
            actor_telegram_id=actor_id,
        )
        return ResetResult(
            mode="member_leave",
            family_id=family.family_id,
            sheet_id=family.sheet_id,
        )

    async def _delete_actor_local_only(self, *, session: AsyncSession, actor_id: int) -> None:
        await session.execute(delete(AuditLog).where(AuditLog.actor_telegram_id == actor_id))
        await session.execute(delete(Invite).where(Invite.created_by_telegram_id == actor_id))
        await session.execute(delete(Invite).where(Invite.used_by_telegram_id == actor_id))
        await session.execute(
            delete(ProcessedReceipt).where(ProcessedReceipt.owner_telegram_id == actor_id)
        )
        await session.execute(
            delete(ExpenseEntry).where(ExpenseEntry.actor_telegram_id == actor_id)
        )
        await session.execute(delete(LedgerEntry).where(LedgerEntry.actor_telegram_id == actor_id))
        await session.execute(
            delete(IdempotencyKey).where(IdempotencyKey.actor_telegram_id == actor_id)
        )
        await session.execute(delete(TelegramUser).where(TelegramUser.telegram_id == actor_id))
