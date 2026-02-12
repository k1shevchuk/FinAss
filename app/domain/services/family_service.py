import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import Settings
from app.domain.entities import InviteCode, JoinResult
from app.domain.services.audit_service import AuditService
from app.domain.value_objects import MembershipRole
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.db.repos.invites_repo import InvitesRepo
from app.infra.db.repos.users_repo import UsersRepo
from app.utils.idempotency import hash_invite_code


class FamilyService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        audit_service: AuditService,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._audit_service = audit_service
        # Uses webhook secret as pepper fallback for invite hashing.
        self._pepper = (
            settings.webhook_secret_token.get_secret_value()
            if settings.webhook_secret_token
            else "default-pepper-change-me"
        )

    async def create_invite(
        self,
        owner_id: int,
        target_username: str | None = None,
        target_telegram_id: int | None = None,
    ) -> InviteCode:
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(owner_id)
            if not family:
                raise ValueError("Семья не найдена.")
            membership = await families_repo.get_membership(
                family_id=family.family_id, telegram_id=owner_id
            )
            if not membership or membership.role != MembershipRole.OWNER.value:
                raise PermissionError("Только владелец семьи может создавать приглашения.")

            code = secrets.token_urlsafe(9)
            code_hash = hash_invite_code(code, self._pepper)
            expires_at_utc = datetime.now(tz=UTC) + timedelta(
                seconds=self._settings.invite_ttl_seconds
            )

            invites_repo = InvitesRepo(session)
            await invites_repo.create_invite(
                family_id=family.family_id,
                code_hash=code_hash,
                created_by_telegram_id=owner_id,
                expires_at_utc=expires_at_utc,
                target_username=target_username,
                target_telegram_id=target_telegram_id,
            )
            await session.commit()

        await self._audit_service.log(
            family_id=family.family_id,
            actor_telegram_id=owner_id,
            action="family.invite.create",
            details_safe_json={
                "target_username": target_username or "",
                "target_telegram_id": str(target_telegram_id) if target_telegram_id else "",
                "expires_at_utc": expires_at_utc.isoformat(),
            },
            sheet_id=family.sheet_id,
        )
        return InviteCode(code=code, expires_at_utc=expires_at_utc)

    async def join_by_code(self, actor_id: int, code: str) -> JoinResult:
        code_hash = hash_invite_code(code, self._pepper)
        now_utc = datetime.now(tz=UTC)

        async with self._session_factory() as session:
            invites_repo = InvitesRepo(session)
            families_repo = FamiliesRepo(session)
            users_repo = UsersRepo(session)

            invite = await invites_repo.get_active_by_hash(code_hash=code_hash, now_utc=now_utc)
            if not invite:
                raise ValueError("Код приглашения недействителен или уже истек.")

            await users_repo.upsert_user(
                telegram_id=actor_id,
                username=None,
                display_name=str(actor_id),
                language_code=None,
            )
            await families_repo.add_member(
                family_id=invite.family_id,
                telegram_id=actor_id,
                role=MembershipRole.EDITOR.value,
                added_by_telegram_id=invite.created_by_telegram_id,
            )
            await invites_repo.use_invite(
                invite=invite, used_by_telegram_id=actor_id, used_at=now_utc
            )
            family = await families_repo.get_by_family_id(invite.family_id)
            await session.commit()
            if not family:
                raise ValueError("Семья не найдена.")

        await self._audit_service.log(
            family_id=family.family_id,
            actor_telegram_id=actor_id,
            action="family.invite.join",
            details_safe_json={"invite_id": str(invite.invite_id)},
            sheet_id=family.sheet_id,
        )
        return JoinResult(family_id=invite.family_id, role=MembershipRole.EDITOR)

    async def remove_member(self, *, owner_id: int, member_telegram_id: int) -> bool:
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(owner_id)
            if not family:
                raise ValueError("Семья не найдена.")
            owner_membership = await families_repo.get_membership(
                family_id=family.family_id, telegram_id=owner_id
            )
            if not owner_membership or owner_membership.role != MembershipRole.OWNER.value:
                raise PermissionError("Только владелец семьи может удалять участников.")
            if member_telegram_id == owner_id:
                raise ValueError("Владелец не может удалить самого себя.")
            removed = await families_repo.remove_member(
                family_id=family.family_id, telegram_id=member_telegram_id
            )
            await session.commit()
            if not removed:
                return False

        await self._audit_service.log(
            family_id=family.family_id,
            actor_telegram_id=owner_id,
            action="family.member.remove",
            details_safe_json={"member_telegram_id": member_telegram_id},
            sheet_id=family.sheet_id,
        )
        return True

    async def list_members(self, actor_id: int) -> list[tuple[int, str]]:
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(actor_id)
            if not family:
                return []
            members = await families_repo.list_members(family.family_id)
            await session.commit()
            return [(m.telegram_id, m.role) for m in members]

    async def get_actor_family(self, actor_id: int) -> tuple[UUID, str, int, str, str] | None:
        async with self._session_factory() as session:
            families_repo = FamiliesRepo(session)
            family = await families_repo.get_family_for_actor(actor_id)
            if not family:
                return None
            await session.commit()
            return (
                family.family_id,
                family.sheet_id,
                family.owner_telegram_id,
                family.timezone,
                family.default_currency,
            )
