import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from arq.connections import ArqRedis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.stdlib import get_logger

from app.domain.services.audit_service import AuditService
from app.infra.db.models import Family, LedgerEntry
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.db.repos.ledger_entries_repo import LedgerEntriesRepo
from app.infra.google.sheets_gateway import GoogleSheetsGateway
from app.utils.timezone import to_local

logger = get_logger(__name__)


class AccountService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        queue: ArqRedis,
        sheets_gateway: GoogleSheetsGateway,
        audit_service: AuditService,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._sheets_gateway = sheets_gateway
        self._audit_service = audit_service

    async def get_balances(self, *, actor_id: int) -> tuple[Decimal, Decimal, str]:
        family = await self._get_family(actor_id)
        if not family:
            raise ValueError("Family is not initialized. Use onboarding first.")
        main_balance = Decimal(str(family.main_balance))
        savings_balance = Decimal(str(family.savings_balance))
        if family.balances_updated_at_utc is None:
            main_balance, savings_balance = await self._bootstrap_balances_from_sheet(
                family=family,
                current_main=main_balance,
                current_savings=savings_balance,
            )
        return main_balance, savings_balance, family.default_currency

    async def initialize_balances(
        self,
        *,
        actor_id: int,
        actor_name: str,
        main_balance: Decimal,
        savings_balance: Decimal,
    ) -> None:
        family: Family
        ledger_rows: list[LedgerEntry]
        async with self._session_factory() as session:
            family = await self._require_owner_family(actor_id=actor_id, session=session)
            family.main_balance = float(main_balance)
            family.savings_balance = float(savings_balance)
            family.balances_updated_at_utc = datetime.now(tz=UTC)
            ledger_rows = self._build_ledger_rows(
                actor_id=actor_id,
                owner_id=family.owner_telegram_id,
                family_id=family.family_id,
                timezone=family.timezone,
                currency=family.default_currency,
                operations=[
                    ("adjust", main_balance, "initial main balance"),
                    ("adjust", savings_balance, "initial savings balance"),
                ],
            )
            await LedgerEntriesRepo(session).add_many(ledger_rows)
            await session.commit()

        await self._enqueue_ledger_rows(sheet_id=family.sheet_id, rows=ledger_rows)
        await self._sync_balances_to_sheet(
            sheet_id=family.sheet_id,
            main_balance=main_balance,
            savings_balance=savings_balance,
        )
        await self._audit_service.log(
            family_id=family.family_id,
            actor_telegram_id=actor_id,
            action="accounts.initialize",
            details_safe_json={
                "main_balance": self._format_decimal(main_balance),
                "savings_balance": self._format_decimal(savings_balance),
                "actor_name": actor_name,
            },
            sheet_id=family.sheet_id,
        )

    async def topup_main(
        self,
        *,
        actor_id: int,
        actor_name: str,
        amount: Decimal,
        note: str | None,
    ) -> tuple[Decimal, Decimal, str]:
        family, new_main, new_savings, currency, ledger_rows = await self._apply_operation(
            actor_id=actor_id,
            amount=amount,
            operation="topup_main",
            note=note,
        )
        await self._audit_service.log(
            family_id=family.family_id,
            actor_telegram_id=actor_id,
            action="accounts.topup_main",
            details_safe_json={
                "amount": self._format_decimal(amount),
                "currency": currency,
                "actor_name": actor_name,
            },
            sheet_id=family.sheet_id,
        )
        await self._enqueue_ledger_rows(sheet_id=family.sheet_id, rows=ledger_rows)
        await self._sync_balances_to_sheet(
            sheet_id=family.sheet_id,
            main_balance=new_main,
            savings_balance=new_savings,
        )
        return new_main, new_savings, currency

    async def transfer_to_savings(
        self,
        *,
        actor_id: int,
        actor_name: str,
        amount: Decimal,
        note: str | None,
    ) -> tuple[Decimal, Decimal, str]:
        family, new_main, new_savings, currency, ledger_rows = await self._apply_operation(
            actor_id=actor_id,
            amount=amount,
            operation="transfer_to_savings",
            note=note,
        )
        await self._audit_service.log(
            family_id=family.family_id,
            actor_telegram_id=actor_id,
            action="accounts.transfer_to_savings",
            details_safe_json={
                "amount": self._format_decimal(amount),
                "currency": currency,
                "actor_name": actor_name,
            },
            sheet_id=family.sheet_id,
        )
        await self._enqueue_ledger_rows(sheet_id=family.sheet_id, rows=ledger_rows)
        await self._sync_balances_to_sheet(
            sheet_id=family.sheet_id,
            main_balance=new_main,
            savings_balance=new_savings,
        )
        return new_main, new_savings, currency

    async def spend_from_savings(
        self,
        *,
        actor_id: int,
        actor_name: str,
        amount: Decimal,
        note: str | None,
    ) -> tuple[Decimal, Decimal, str]:
        family, new_main, new_savings, currency, ledger_rows = await self._apply_operation(
            actor_id=actor_id,
            amount=amount,
            operation="spend_from_savings",
            note=note,
        )
        await self._audit_service.log(
            family_id=family.family_id,
            actor_telegram_id=actor_id,
            action="accounts.spend_from_savings",
            details_safe_json={
                "amount": self._format_decimal(amount),
                "currency": currency,
                "actor_name": actor_name,
            },
            sheet_id=family.sheet_id,
        )
        await self._enqueue_ledger_rows(sheet_id=family.sheet_id, rows=ledger_rows)
        await self._sync_balances_to_sheet(
            sheet_id=family.sheet_id,
            main_balance=new_main,
            savings_balance=new_savings,
        )
        return new_main, new_savings, currency

    async def _apply_operation(
        self,
        *,
        actor_id: int,
        amount: Decimal,
        operation: str,
        note: str | None,
    ) -> tuple[Family, Decimal, Decimal, str, list[LedgerEntry]]:
        if amount <= Decimal("0"):
            raise ValueError("Сумма должна быть больше нуля.")
        async with self._session_factory() as session:
            family = await self._require_owner_family(actor_id=actor_id, session=session)
            current_main = Decimal(str(family.main_balance))
            current_savings = Decimal(str(family.savings_balance))
            currency = family.default_currency

            if operation == "topup_main":
                new_main = current_main + amount
                new_savings = current_savings
                entry_type = "topup_main"
            elif operation == "transfer_to_savings":
                if amount > current_main:
                    raise ValueError("Недостаточно средств на основном счете.")
                new_main = current_main - amount
                new_savings = current_savings + amount
                entry_type = "transfer_to_savings"
            elif operation == "spend_from_savings":
                if amount > current_savings:
                    raise ValueError("Недостаточно средств на накопительном счете.")
                new_main = current_main
                new_savings = current_savings - amount
                entry_type = "spend_from_savings"
            else:
                raise ValueError("Unsupported account operation.")

            family.main_balance = float(new_main)
            family.savings_balance = float(new_savings)
            family.balances_updated_at_utc = datetime.now(tz=UTC)

            ledger_rows = self._build_ledger_rows(
                actor_id=actor_id,
                owner_id=family.owner_telegram_id,
                family_id=family.family_id,
                timezone=family.timezone,
                currency=currency,
                operations=[(entry_type, amount, note)],
            )
            await LedgerEntriesRepo(session).add_many(ledger_rows)
            await session.commit()
            return family, new_main, new_savings, currency, ledger_rows

    async def _get_family(self, actor_id: int) -> Family | None:
        async with self._session_factory() as session:
            family = await FamiliesRepo(session).get_family_for_actor(actor_id)
            await session.commit()
            return family

    async def _require_owner_family(self, *, actor_id: int, session: AsyncSession) -> Family:
        families_repo = FamiliesRepo(session)
        family = await families_repo.get_family_for_actor(actor_id)
        if not family:
            raise ValueError("Family is not initialized. Use onboarding first.")
        if actor_id != family.owner_telegram_id:
            raise PermissionError("Only owner can change balances.")
        return family

    async def _bootstrap_balances_from_sheet(
        self,
        *,
        family: Family,
        current_main: Decimal,
        current_savings: Decimal,
    ) -> tuple[Decimal, Decimal]:
        try:
            settings = await self._sheets_gateway.get_settings(sheet_id=family.sheet_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("accounts.bootstrap_balances.failed", error=str(exc))
            return current_main, current_savings

        main_balance = self._parse_decimal(settings.get("main_balance", str(current_main)))
        savings_balance = self._parse_decimal(settings.get("savings_balance", str(current_savings)))

        async with self._session_factory() as session:
            db_family = await FamiliesRepo(session).get_by_family_id(family.family_id)
            if db_family:
                db_family.main_balance = float(main_balance)
                db_family.savings_balance = float(savings_balance)
                db_family.balances_updated_at_utc = datetime.now(tz=UTC)
            await session.commit()
        return main_balance, savings_balance

    async def _sync_balances_to_sheet(
        self,
        *,
        sheet_id: str,
        main_balance: Decimal,
        savings_balance: Decimal,
    ) -> None:
        now_utc = datetime.now(tz=UTC).isoformat()
        try:
            await self._sheets_gateway.set_setting(
                sheet_id=sheet_id,
                key="main_balance",
                value=self._format_decimal(main_balance),
            )
            await self._sheets_gateway.set_setting(
                sheet_id=sheet_id,
                key="savings_balance",
                value=self._format_decimal(savings_balance),
            )
            await self._sheets_gateway.set_setting(
                sheet_id=sheet_id,
                key="updated_at_utc",
                value=now_utc,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("accounts.sync_sheet_balances.failed", error=str(exc))

    async def _enqueue_ledger_rows(self, *, sheet_id: str, rows: list[LedgerEntry]) -> None:
        payload = [
            self._to_sheet_row(row) for row in rows if self._parse_decimal(str(row.amount)) > 0
        ]
        if not payload:
            return
        await self._queue.enqueue_job("append_ledger_job", sheet_id, payload)

    def _build_ledger_rows(
        self,
        *,
        actor_id: int,
        owner_id: int,
        family_id,
        timezone: str,
        currency: str,
        operations: list[tuple[str, Decimal, str | None]],
    ) -> list[LedgerEntry]:
        out: list[LedgerEntry] = []
        for entry_type, amount, note in operations:
            now_utc = datetime.now(tz=UTC)
            local_dt = to_local(now_utc, timezone)
            out.append(
                LedgerEntry(
                    entry_id=str(uuid.uuid4()),
                    at_utc=now_utc,
                    local_datetime=local_dt,
                    timezone=timezone,
                    actor_telegram_id=actor_id,
                    owner_telegram_id=owner_id,
                    family_id=family_id,
                    type=entry_type,
                    amount=float(amount),
                    currency=currency,
                    note=note or "",
                )
            )
        return out

    @staticmethod
    def _to_sheet_row(row: LedgerEntry) -> list[str]:
        return [
            row.entry_id,
            row.at_utc.isoformat(),
            row.local_datetime.isoformat(),
            row.timezone,
            str(row.actor_telegram_id),
            str(row.owner_telegram_id),
            row.type,
            f"{row.amount}",
            row.currency,
            row.note or "",
        ]

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        try:
            return Decimal(str(value).strip() or "0")
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @staticmethod
    def _format_decimal(value: Decimal) -> str:
        return f"{value.quantize(Decimal('0.01'))}"
