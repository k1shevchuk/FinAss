import asyncio
import inspect
from dataclasses import dataclass

import uvicorn
from aiogram import Bot, Dispatcher
from arq.connections import ArqRedis, RedisSettings, create_pool
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from structlog.stdlib import get_logger

from app.api.webhook import build_api_app
from app.bot.handlers import setup_routers
from app.bot.middlewares.authz import AuthzGuard, PrivateChatOnlyMiddleware
from app.bot.middlewares.correlation import CorrelationMiddleware
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.config.logging import configure_logging
from app.config.settings import Settings, get_settings
from app.domain.services.account_service import AccountService
from app.domain.services.audit_service import AuditService
from app.domain.services.category_matcher_service import CategoryMatcherService
from app.domain.services.category_service import CategoryService
from app.domain.services.container import AppServices
from app.domain.services.expense_service import ExpenseService
from app.domain.services.family_service import FamilyService
from app.domain.services.idempotency_service import IdempotencyService
from app.domain.services.onboarding_service import OnboardingService
from app.domain.services.receipt_service import ReceiptService
from app.domain.services.report_service import ReportService
from app.domain.services.reset_service import ResetService
from app.domain.services.settings_service import SettingsService
from app.infra.db.session import create_engine, create_session_factory
from app.infra.google.drive_sharing import DriveSharing
from app.infra.google.google_client_factory import GoogleClientFactory
from app.infra.google.sheets_gateway import GoogleSheetsGateway
from app.infra.receipt.pipeline import ReceiptPipeline
from app.infra.receipt.providers.fallback import FallbackReceiptProvider
from app.infra.receipt.providers.proverkacheka import ProverkachekaReceiptProvider
from app.infra.receipt.qr_decode import QrDecoder
from app.infra.telegram.file_downloader import TelegramFileDownloader
from app.utils.rate_limit import RedisRateLimiter

logger = get_logger(__name__)


@dataclass(slots=True)
class Runtime:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis
    arq_pool: ArqRedis
    bot: Bot
    dispatcher: Dispatcher
    services: AppServices

    async def close(self) -> None:
        await self.bot.session.close()
        await _aclose_or_close(self.redis)
        await _aclose_or_close(self.arq_pool)
        await self.engine.dispose()


async def _aclose_or_close(resource: object) -> None:
    aclose = getattr(resource, "aclose", None)
    if callable(aclose):
        result = aclose()
        if inspect.isawaitable(result):
            await result
        return
    close = getattr(resource, "close", None)
    if callable(close):
        result = close()
        if inspect.isawaitable(result):
            await result


async def build_runtime(settings: Settings) -> Runtime:
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    bot = Bot(token=settings.telegram_bot_token.get_secret_value())
    dispatcher = Dispatcher()

    client_factory = GoogleClientFactory(settings)
    sheets_service = client_factory.build_sheets_service()
    drive_service = client_factory.build_drive_service()
    drive_sharing = DriveSharing(
        drive_service=drive_service,
        max_attempts=settings.google_api_retry_max_attempts,
        base_delay=settings.google_api_retry_base_delay_seconds,
        max_delay=settings.google_api_retry_max_delay_seconds,
    )
    sheets_gateway = GoogleSheetsGateway(
        sheets_service=sheets_service,
        drive_service=drive_service,
        drive_sharing=drive_sharing,
        settings=settings,
    )

    downloader = TelegramFileDownloader(
        bot=bot,
        max_file_size_bytes=settings.qr_max_file_size_bytes,
        download_timeout_seconds=settings.telegram_download_timeout_seconds,
    )
    decoder = QrDecoder(
        max_pixels=settings.qr_max_pixels,
        decode_timeout_seconds=settings.qr_decode_timeout_seconds,
    )
    provider = FallbackReceiptProvider()
    provider_token = (
        settings.receipt_provider_api_token.get_secret_value().strip()
        if settings.receipt_provider_api_token is not None
        else ""
    )
    if settings.receipt_items_provider == "proverkacheka" and provider_token:
        provider = ProverkachekaReceiptProvider(
            api_token=provider_token,
            base_url=settings.receipt_provider_base_url,
            timeout_seconds=settings.receipt_provider_timeout_seconds,
        )
        logger.info(
            "receipt.provider.enabled",
            provider="proverkacheka",
            timeout_seconds=settings.receipt_provider_timeout_seconds,
            base_url=settings.receipt_provider_base_url,
        )
    elif settings.receipt_items_provider == "proverkacheka":
        logger.warning(
            "receipt.provider.disabled.missing_token",
            receipt_items_provider=settings.receipt_items_provider,
        )
    else:
        logger.info(
            "receipt.provider.enabled",
            provider="fallback",
            reason="configured_none",
        )
    receipt_pipeline = ReceiptPipeline(
        downloader=downloader,
        decoder=decoder,
        provider=provider,
    )

    audit_service = AuditService(session_factory=session_factory, queue=arq_pool)
    category_service = CategoryService(
        session_factory=session_factory,
        redis=redis,
        sheets_gateway=sheets_gateway,
        settings=settings,
    )
    category_matcher = CategoryMatcherService(
        category_service=category_service,
        cache_ttl_seconds=settings.cache_ttl_seconds,
    )

    services = AppServices(
        onboarding=OnboardingService(
            session_factory=session_factory,
            sheets_gateway=sheets_gateway,
            settings=settings,
        ),
        expense=ExpenseService(
            session_factory=session_factory,
            queue=arq_pool,
            audit_service=audit_service,
        ),
        accounts=AccountService(
            session_factory=session_factory,
            queue=arq_pool,
            sheets_gateway=sheets_gateway,
            audit_service=audit_service,
        ),
        receipt=ReceiptService(session_factory=session_factory, pipeline=receipt_pipeline),
        report=ReportService(
            session_factory=session_factory,
            redis=redis,
            sheets_gateway=sheets_gateway,
            settings=settings,
        ),
        family=FamilyService(
            session_factory=session_factory,
            settings=settings,
            audit_service=audit_service,
        ),
        categories=category_service,
        category_matcher=category_matcher,
        settings=SettingsService(
            session_factory=session_factory,
            redis=redis,
            sheets_gateway=sheets_gateway,
            settings=settings,
        ),
        reset=ResetService(
            session_factory=session_factory,
            sheets_gateway=sheets_gateway,
        ),
        audit=audit_service,
        idempotency=IdempotencyService(session_factory=session_factory),
        authz_guard=AuthzGuard(session_factory),
    )

    limiter = RedisRateLimiter(redis)
    dispatcher.update.middleware(CorrelationMiddleware())
    dispatcher.update.middleware(PrivateChatOnlyMiddleware())
    dispatcher.update.middleware(
        RateLimitMiddleware(
            limiter=limiter,
            user_limit_per_min=settings.rate_limit_user_per_min,
            chat_limit_per_min=settings.rate_limit_chat_per_min,
            scan_limit_per_10min=settings.rate_limit_scan_per_10min,
        )
    )
    dispatcher.include_router(setup_routers())
    dispatcher.workflow_data["services"] = services
    return Runtime(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis,
        arq_pool=arq_pool,
        bot=bot,
        dispatcher=dispatcher,
        services=services,
    )


async def run_polling(runtime: Runtime) -> None:
    logger.info("bot.run_polling.start")
    await runtime.dispatcher.start_polling(runtime.bot)


async def run_webhook(runtime: Runtime) -> None:
    if not runtime.settings.base_url:
        raise ValueError("BASE_URL is required for webhook mode.")
    base_url = runtime.settings.base_url
    app = build_api_app(bot=runtime.bot, dispatcher=runtime.dispatcher, settings=runtime.settings)

    @app.on_event("startup")
    async def on_startup() -> None:
        webhook_url = f"{base_url.rstrip('/')}/telegram/webhook"
        await runtime.bot.set_webhook(
            url=webhook_url,
            secret_token=(
                runtime.settings.webhook_secret_token.get_secret_value()
                if runtime.settings.webhook_secret_token
                else None
            ),
            drop_pending_updates=False,
        )
        logger.info("bot.webhook.set", webhook_url=webhook_url)

    @app.on_event("shutdown")
    async def on_shutdown() -> None:
        await runtime.close()

    config = uvicorn.Config(
        app, host="0.0.0.0", port=8000, log_level=runtime.settings.log_level.lower()
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_polling_mode(settings: Settings) -> None:
    runtime = await build_runtime(settings)
    try:
        await run_polling(runtime)
    finally:
        await runtime.close()


async def run_webhook_mode(settings: Settings) -> None:
    runtime = await build_runtime(settings)
    await run_webhook(runtime)


def main() -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.json_logs)
    if settings.app_mode == "webhook":
        asyncio.run(run_webhook_mode(settings))
        return

    asyncio.run(run_polling_mode(settings))


if __name__ == "__main__":
    main()
