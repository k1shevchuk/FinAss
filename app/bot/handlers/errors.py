from contextlib import suppress

from aiogram import Router
from aiogram.types import CallbackQuery, Message
from aiogram.types.error_event import ErrorEvent
from structlog.stdlib import get_logger

router = Router()
logger = get_logger(__name__)


@router.error()
async def global_error_handler(event: ErrorEvent) -> bool:
    update = event.update
    logger.exception(
        "telegram.update.failed",
        update_id=getattr(update, "update_id", None),
        error=str(event.exception),
    )

    try:
        if isinstance(update.message, Message):
            await update.message.answer(
                "Произошла ошибка при обработке запроса. Попробуйте еще раз или нажмите «Меню»."
            )
            return True

        callback = update.callback_query
        if isinstance(callback, CallbackQuery) and isinstance(callback.message, Message):
            with suppress(Exception):
                await callback.answer("Ошибка обработки", show_alert=True)
            await callback.message.answer(
                "Произошла ошибка при обработке запроса. Попробуйте снова или откройте «Меню»."
            )
            return True
    except Exception as notify_exc:  # noqa: BLE001
        logger.warning("telegram.update.failed_notify_user", error=str(notify_exc))

    return True
