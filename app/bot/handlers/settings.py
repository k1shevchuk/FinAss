from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.menu import BTN_SETTINGS, main_menu_keyboard
from app.bot.states.settings import SettingsStates
from app.domain.services.container import AppServices

router = Router()


def settings_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="💱 Валюта", callback_data="set:currency")
    builder.button(text="🕒 Часовой пояс", callback_data="set:timezone")
    builder.button(text="🔢 Округление", callback_data="set:rounding")
    builder.button(text="🏠 Меню", callback_data="set:menu")
    builder.adjust(2, 2)
    return builder.as_markup()


def rounding_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="HALF_UP", callback_data="set:rounding:HALF_UP")
    builder.button(text="HALF_EVEN", callback_data="set:rounding:HALF_EVEN")
    builder.button(text="DOWN", callback_data="set:rounding:DOWN")
    builder.button(text="⬅️ Назад", callback_data="set:refresh")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


async def _send_settings_panel(message: Message, services: AppServices, actor_id: int) -> None:
    settings = await services.settings.get_settings(actor_id)
    if not settings:
        await message.answer("Настройки пока недоступны. Сначала пройдите онбординг.")
        return
    await message.answer(
        "Текущие настройки:\n"
        f"• Валюта: {settings.get('currency', 'RUB')}\n"
        f"• Часовой пояс: {settings.get('timezone', 'UTC')}\n"
        f"• Округление: {settings.get('rounding_mode', 'HALF_UP')}\n\n"
        "Выберите, что изменить:",
        reply_markup=settings_actions_keyboard(),
    )


@router.message(Command("settings"))
@router.message(F.text == BTN_SETTINGS)
async def settings_start(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    await state.clear()
    await _send_settings_panel(message, services, user.id)


@router.callback_query(F.data == "set:refresh")
async def settings_refresh(
    callback: CallbackQuery, state: FSMContext, services: AppServices
) -> None:
    user = callback.from_user
    if not isinstance(callback.message, Message) or not user:
        return
    await state.clear()
    await _send_settings_panel(callback.message, services, user.id)
    await callback.answer()


@router.callback_query(F.data == "set:currency")
async def settings_currency_request(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsStates.waiting_currency)
    if callback.message:
        await callback.message.answer("Введите код валюты, например: RUB, USD, EUR")
    await callback.answer()


@router.callback_query(F.data == "set:timezone")
async def settings_timezone_request(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SettingsStates.waiting_timezone)
    if callback.message:
        await callback.message.answer("Введите часовой пояс, например: Europe/Moscow")
    await callback.answer()


@router.callback_query(F.data == "set:rounding")
async def settings_rounding_request(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.answer(
            "Выберите режим округления:",
            reply_markup=rounding_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("set:rounding:"))
async def settings_rounding_commit(callback: CallbackQuery, services: AppServices) -> None:
    user = callback.from_user
    if not isinstance(callback.message, Message) or not user or not callback.data:
        return
    value = callback.data.rsplit(":", maxsplit=1)[1]
    if value not in {"HALF_UP", "HALF_EVEN", "DOWN"}:
        await callback.answer("Неверный режим", show_alert=True)
        return

    await services.settings.set_setting(user.id, "rounding_mode", value)
    await callback.message.answer("Режим округления обновлен.")
    await _send_settings_panel(callback.message, services, user.id)
    await callback.answer()


@router.callback_query(F.data == "set:menu")
async def settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.message(SettingsStates.waiting_currency, F.text)
async def settings_currency_commit(
    message: Message,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    value = message.text.strip().upper()
    if len(value) < 3 or len(value) > 8:
        await message.answer("Некорректная валюта.")
        return

    await services.settings.set_setting(user.id, "currency", value)
    await state.clear()
    await message.answer("Валюта обновлена.")
    await _send_settings_panel(message, services, user.id)


@router.message(SettingsStates.waiting_timezone, F.text)
async def settings_timezone_commit(
    message: Message,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    value = message.text.strip()
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        await message.answer("Некорректный часовой пояс. Пример: Europe/Moscow")
        return

    await services.settings.set_setting(user.id, "timezone", value)
    await state.clear()
    await message.answer("Часовой пояс обновлен.")
    await _send_settings_panel(message, services, user.id)
