from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from structlog.stdlib import get_logger

from app.api.health import router as health_router
from app.api.metrics import router as metrics_router
from app.api.metrics import telegram_updates_total
from app.config.settings import Settings

logger = get_logger(__name__)


def build_api_app(*, bot: Bot, dispatcher: Dispatcher, settings: Settings) -> FastAPI:
    app = FastAPI(title="Expense Tracker Bot API", version="0.1.0")
    app.include_router(health_router)
    app.include_router(metrics_router)

    @app.post("/telegram/webhook")
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        if settings.webhook_secret_token:
            expected = settings.webhook_secret_token.get_secret_value()
            if x_telegram_bot_api_secret_token != expected:
                raise HTTPException(status_code=403, detail="Invalid webhook secret token")

        payload: dict[str, Any] = await request.json()
        update = Update.model_validate(payload)
        telegram_updates_total.inc()
        await dispatcher.feed_update(bot=bot, update=update)
        return {"ok": True}

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "expense-tracker-bot", "mode": settings.app_mode}

    logger.info("api.webhook.app_built", mode=settings.app_mode)
    return app
