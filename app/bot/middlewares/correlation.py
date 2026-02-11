from collections.abc import Awaitable, Callable
from contextlib import suppress
from uuid import uuid4

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update


class CorrelationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[object]],
        event: TelegramObject,
        data: dict,
    ) -> object:
        correlation_id = str(uuid4())
        if isinstance(event, Update) and event.update_id is not None:
            correlation_id = str(event.update_id)
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        try:
            return await handler(event, data)
        finally:
            with suppress(Exception):
                structlog.contextvars.clear_contextvars()
