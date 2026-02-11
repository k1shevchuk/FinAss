from arq.connections import RedisSettings
from structlog.stdlib import get_logger

from app.config.settings import Settings, get_settings
from app.infra.google.drive_sharing import DriveSharing
from app.infra.google.google_client_factory import GoogleClientFactory
from app.infra.google.sheets_gateway import GoogleSheetsGateway
from app.infra.queue.arq_jobs import (
    append_audit_job,
    append_expenses_job,
    append_ledger_job,
    sync_users_sheet_job,
)

logger = get_logger(__name__)


async def startup(ctx: dict[str, object]) -> None:
    settings = get_settings()
    client_factory = GoogleClientFactory(settings)
    sheets = client_factory.build_sheets_service()
    drive = client_factory.build_drive_service()
    drive_sharing = DriveSharing(
        drive_service=drive,
        max_attempts=settings.google_api_retry_max_attempts,
        base_delay=settings.google_api_retry_base_delay_seconds,
        max_delay=settings.google_api_retry_max_delay_seconds,
    )
    ctx["sheets_gateway"] = GoogleSheetsGateway(
        sheets_service=sheets,
        drive_service=drive,
        drive_sharing=drive_sharing,
        settings=settings,
    )
    logger.info("arq.worker.startup")


async def shutdown(ctx: dict[str, object]) -> None:
    logger.info("arq.worker.shutdown")


class WorkerSettings:
    settings: Settings = get_settings()
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [append_expenses_job, append_audit_job, append_ledger_job, sync_users_sheet_job]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 50
