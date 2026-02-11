from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.bot.keyboards.menu import BTN_SCAN
from app.utils.rate_limit import LimitWindow, RedisRateLimiter


class RateLimitMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        limiter: RedisRateLimiter,
        user_limit_per_min: int,
        chat_limit_per_min: int,
        scan_limit_per_10min: int,
    ) -> None:
        self._limiter = limiter
        self._user_limit = user_limit_per_min
        self._chat_limit = chat_limit_per_min
        self._scan_limit = scan_limit_per_10min

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[object]],
        event: TelegramObject,
        data: dict,
    ) -> object:
        message: Message | None = None
        if isinstance(event, Message):
            message = event
        elif isinstance(event, CallbackQuery):
            message = event.message if isinstance(event.message, Message) else None

        if message and message.from_user and message.chat:
            user_window = LimitWindow(
                key=f"user:{message.from_user.id}",
                limit=self._user_limit,
                ttl_seconds=60,
            )
            chat_window = LimitWindow(
                key=f"chat:{message.chat.id}",
                limit=self._chat_limit,
                ttl_seconds=60,
            )
            if not await self._limiter.hit(user_window) or not await self._limiter.hit(chat_window):
                await message.answer("Слишком много запросов. Попробуйте через минуту.")
                return None

            if message.text and (message.text.startswith("/scan") or message.text == BTN_SCAN):
                scan_window = LimitWindow(
                    key=f"scan:{message.from_user.id}",
                    limit=self._scan_limit,
                    ttl_seconds=600,
                )
                if not await self._limiter.hit(scan_window):
                    await message.answer("Лимит сканирования чеков превышен. Попробуйте позже.")
                    return None

        return await handler(event, data)
