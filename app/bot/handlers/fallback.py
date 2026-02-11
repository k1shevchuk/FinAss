from contextlib import suppress

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.menu import main_menu_keyboard, onboarding_mode_keyboard
from app.domain.services.container import AppServices

router = Router()


@router.callback_query()
async def fallback_callback(callback: CallbackQuery, services: AppServices) -> None:
    user = callback.from_user
    with suppress(Exception):
        await callback.answer("Кнопка устарела. Откройте актуальное меню.", show_alert=True)
    if isinstance(callback.message, Message):
        if user and await services.family.get_actor_family(user.id):
            markup = main_menu_keyboard()
        else:
            markup = onboarding_mode_keyboard()
        await callback.message.answer("Выберите действие из актуального меню.", reply_markup=markup)


@router.message()
async def fallback_message(message: Message, services: AppServices) -> None:
    user = message.from_user
    if user and await services.family.get_actor_family(user.id):
        markup = main_menu_keyboard()
    else:
        markup = onboarding_mode_keyboard()
    await message.answer("Не понял запрос. Используйте кнопки меню ниже.", reply_markup=markup)
