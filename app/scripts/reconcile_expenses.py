from __future__ import annotations

import asyncio
from collections.abc import Iterable

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config.settings import get_settings
from app.domain.entities import ExpenseRow
from app.infra.db.repos.expense_entries_repo import ExpenseEntriesRepo
from app.infra.db.repos.families_repo import FamiliesRepo
from app.infra.google.drive_sharing import DriveSharing
from app.infra.google.google_client_factory import GoogleClientFactory
from app.infra.google.sheets_gateway import GoogleSheetsGateway


def _chunks[T](items: list[T], size: int) -> Iterable[list[T]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def _to_sheet_row(expense) -> list[str]:  # type: ignore[no-untyped-def]
    return [
        expense.expense_id,
        expense.created_at_utc.isoformat(),
        expense.local_datetime.isoformat(),
        expense.timezone,
        str(expense.actor_telegram_id),
        expense.actor_name,
        str(expense.owner_telegram_id),
        str(expense.family_id),
        expense.source,
        expense.receipt_hash or "",
        expense.item_name,
        f"{expense.quantity}",
        f"{expense.unit_price}",
        f"{expense.total_price}",
        expense.currency,
        expense.category,
        expense.merchant or "",
        expense.notes or "",
    ]


async def _run() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.db_dsn)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    client_factory = GoogleClientFactory(settings)
    sheets = client_factory.build_sheets_service()
    drive = client_factory.build_drive_service()
    gateway = GoogleSheetsGateway(
        sheets_service=sheets,
        drive_service=drive,
        drive_sharing=DriveSharing(
            drive_service=drive,
            max_attempts=settings.google_api_retry_max_attempts,
            base_delay=settings.google_api_retry_base_delay_seconds,
            max_delay=settings.google_api_retry_max_delay_seconds,
        ),
        settings=settings,
    )

    try:
        async with session_factory() as session:
            families = await FamiliesRepo(session).list_all()
            await session.commit()

        total_missing = 0
        for family in families:
            async with session_factory() as session:
                rows = await ExpenseEntriesRepo(session).list_by_family(family_id=family.family_id)
                await session.commit()

            if not rows:
                continue

            sheet_rows = await gateway.read_expenses(sheet_id=family.sheet_id)
            existing_ids = {
                str(item.get("expense_id", "")).strip()
                for item in sheet_rows
                if str(item.get("expense_id", "")).strip()
            }

            missing = [row for row in rows if row.expense_id not in existing_ids]
            if not missing:
                continue

            print(
                f"[reconcile] family={family.family_id} sheet={family.sheet_id} missing={len(missing)}"
            )

            for batch in _chunks(missing, 200):
                payload = [ExpenseRow(values=_to_sheet_row(item)) for item in batch]
                await gateway.append_expenses(sheet_id=family.sheet_id, rows=payload)

            total_missing += len(missing)

        print(f"[reconcile] done, appended_missing_rows={total_missing}")
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
