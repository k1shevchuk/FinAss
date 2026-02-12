from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.menu import (
    BTN_CANCEL,
    BTN_MENU,
    BTN_RESTART,
    main_menu_keyboard,
    onboarding_mode_keyboard,
)
from app.domain.services.container import AppServices

router = Router()


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cancel_command(message: Message, state: FSMContext, services: AppServices) -> None:
    await state.clear()
    user = message.from_user
    if not user:
        return
    actor_family = await services.family.get_actor_family(user.id)
    if actor_family:
        await message.answer("Операция отменена.", reply_markup=main_menu_keyboard())
        return
    await message.answer("Операция отменена.", reply_markup=onboarding_mode_keyboard())


@router.message(Command("restart"))
@router.message(F.text == BTN_RESTART)
async def restart_command(message: Message, state: FSMContext, services: AppServices) -> None:
    await state.clear()
    user = message.from_user
    if not user:
        return
    actor_family = await services.family.get_actor_family(user.id)
    if actor_family:
        await message.answer("Сессия перезапущена. Главное меню:", reply_markup=main_menu_keyboard())
        return
    await message.answer("Сессия перезапущена. Выберите действие:", reply_markup=onboarding_mode_keyboard())


@router.message(F.text == BTN_MENU)
async def menu_command(message: Message, state: FSMContext, services: AppServices) -> None:
    await state.clear()
    user = message.from_user
    if not user:
        return
    actor_family = await services.family.get_actor_family(user.id)
    if actor_family:
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
        return
    await message.answer(
        "Сначала подключите Google Таблицу.", reply_markup=onboarding_mode_keyboard()
    )


@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Операция отменена.")
    await callback.answer()
