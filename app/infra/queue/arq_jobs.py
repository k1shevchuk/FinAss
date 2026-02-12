import ssl
from typing import Any

from arq.worker import Retry
from googleapiclient.errors import HttpError
from structlog.stdlib import get_logger

from app.domain.entities import AuditRow, ExpenseRow

logger = get_logger(__name__)


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, ssl.SSLError):
        return True
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, OSError):
        return True
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, "status", None)
        return status in {408, 409, 425, 429, 500, 502, 503, 504}
    return False


async def append_expenses_job(ctx: dict[str, Any], sheet_id: str, rows: list[list[str]]) -> int:
    gateway = ctx["sheets_gateway"]
    payload = [ExpenseRow(values=r) for r in rows]
    try:
        result = await gateway.append_expenses(sheet_id=sheet_id, rows=payload)
        logger.info("jobs.append_expenses.done", sheet_id=sheet_id, updated_rows=result.updated_rows)
        return int(result.updated_rows)
    except Exception as exc:  # noqa: BLE001
        if _is_transient_error(exc):
            logger.warning(
                "jobs.append_expenses.retrying",
                sheet_id=sheet_id,
                error=str(exc),
            )
            raise Retry(defer=30) from exc
        status = getattr(getattr(exc, "resp", None), "status", None)
        logger.error(
            "jobs.append_expenses.failed",
            sheet_id=sheet_id,
            rows=len(rows),
            status=status,
            error=str(exc),
        )
        raise


async def append_audit_job(ctx: dict[str, Any], sheet_id: str, rows: list[list[str]]) -> int:
    gateway = ctx["sheets_gateway"]
    payload = [AuditRow(values=r) for r in rows]
    try:
        result = await gateway.append_audit(sheet_id=sheet_id, rows=payload)
        logger.info("jobs.append_audit.done", sheet_id=sheet_id, updated_rows=result.updated_rows)
        return int(result.updated_rows)
    except Exception as exc:  # noqa: BLE001
        if _is_transient_error(exc):
            logger.warning(
                "jobs.append_audit.retrying",
                sheet_id=sheet_id,
                error=str(exc),
            )
            raise Retry(defer=30) from exc
        raise


async def append_ledger_job(ctx: dict[str, Any], sheet_id: str, rows: list[list[str]]) -> int:
    gateway = ctx["sheets_gateway"]
    try:
        result = await gateway.append_ledger(sheet_id=sheet_id, rows=rows)
        logger.info("jobs.append_ledger.done", sheet_id=sheet_id, updated_rows=result.updated_rows)
        return int(result.updated_rows)
    except Exception as exc:  # noqa: BLE001
        if _is_transient_error(exc):
            logger.warning(
                "jobs.append_ledger.retrying",
                sheet_id=sheet_id,
                error=str(exc),
            )
            raise Retry(defer=30) from exc
        raise


async def sync_users_sheet_job(ctx: dict[str, Any], sheet_id: str, rows: list[list[str]]) -> int:
    gateway = ctx["sheets_gateway"]
    try:
        result = await gateway.append_users(sheet_id=sheet_id, rows=rows)
        logger.info("jobs.sync_users_sheet.done", sheet_id=sheet_id, updated_rows=result.updated_rows)
        return int(result.updated_rows)
    except Exception as exc:  # noqa: BLE001
        if _is_transient_error(exc):
            logger.warning(
                "jobs.sync_users_sheet.retrying",
                sheet_id=sheet_id,
                error=str(exc),
            )
            raise Retry(defer=30) from exc
        raise
