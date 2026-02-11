from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.domain.services.container import AppServices

router = Router()


@router.message(Command("settings"))
async def settings_command(message: Message, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    text = (message.text or "").strip()
    tokens = text.split(maxsplit=2)
    if len(tokens) == 1:
        settings = await services.settings.get_settings(user.id)
        if not settings:
            await message.answer("Настройки не найдены. Выполните /start.")
            return
        await message.answer(
            "Текущие настройки:\n"
            f"- currency: {settings.get('currency', 'RUB')}\n"
            f"- timezone: {settings.get('timezone', 'UTC')}\n"
            f"- rounding_mode: {settings.get('rounding_mode', 'HALF_UP')}\n\n"
            "Изменение:\n"
            "/settings currency USD\n"
            "/settings timezone Europe/Berlin\n"
            "/settings rounding HALF_UP"
        )
        return

    if len(tokens) < 3:
        await message.answer("Формат: /settings <currency|timezone|rounding> <value>")
        return
    key = tokens[1].lower()
    value = tokens[2].strip()
    if key == "currency":
        if len(value) < 3 or len(value) > 8:
            await message.answer("Некорректная валюта.")
            return
        await services.settings.set_setting(user.id, "currency", value.upper())
    elif key == "timezone":
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            await message.answer("Некорректная timezone. Пример: Europe/Moscow")
            return
        await services.settings.set_setting(user.id, "timezone", value)
    elif key == "rounding":
        if value not in {"HALF_UP", "HALF_EVEN", "DOWN"}:
            await message.answer("Доступно: HALF_UP, HALF_EVEN, DOWN")
            return
        await services.settings.set_setting(user.id, "rounding_mode", value)
    else:
        await message.answer("Ключ не поддерживается. Используйте currency/timezone/rounding.")
        return

    await message.answer("Настройка обновлена.")
