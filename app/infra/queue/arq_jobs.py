from typing import Any

from structlog.stdlib import get_logger

from app.domain.entities import AuditRow, ExpenseRow

logger = get_logger(__name__)


async def append_expenses_job(ctx: dict[str, Any], sheet_id: str, rows: list[list[str]]) -> int:
    gateway = ctx["sheets_gateway"]
    payload = [ExpenseRow(values=r) for r in rows]
    result = await gateway.append_expenses(sheet_id=sheet_id, rows=payload)
    logger.info("jobs.append_expenses.done", sheet_id=sheet_id, updated_rows=result.updated_rows)
    return int(result.updated_rows)


async def append_audit_job(ctx: dict[str, Any], sheet_id: str, rows: list[list[str]]) -> int:
    gateway = ctx["sheets_gateway"]
    payload = [AuditRow(values=r) for r in rows]
    result = await gateway.append_audit(sheet_id=sheet_id, rows=payload)
    logger.info("jobs.append_audit.done", sheet_id=sheet_id, updated_rows=result.updated_rows)
    return int(result.updated_rows)


async def append_ledger_job(ctx: dict[str, Any], sheet_id: str, rows: list[list[str]]) -> int:
    gateway = ctx["sheets_gateway"]
    result = await gateway.append_ledger(sheet_id=sheet_id, rows=rows)
    logger.info("jobs.append_ledger.done", sheet_id=sheet_id, updated_rows=result.updated_rows)
    return int(result.updated_rows)


async def sync_users_sheet_job(ctx: dict[str, Any], sheet_id: str, rows: list[list[str]]) -> int:
    gateway = ctx["sheets_gateway"]
    result = await gateway.append_users(sheet_id=sheet_id, rows=rows)
    logger.info("jobs.sync_users_sheet.done", sheet_id=sheet_id, updated_rows=result.updated_rows)
    return int(result.updated_rows)
