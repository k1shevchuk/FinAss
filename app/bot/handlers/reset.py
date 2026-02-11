from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.common import confirm_keyboard
from app.bot.keyboards.menu import BTN_RESET, main_menu_keyboard, onboarding_mode_keyboard
from app.bot.states.onboarding import OnboardingStates
from app.bot.states.reset import ResetStates
from app.domain.services.container import AppServices
from app.utils.idempotency import sha256_hex

router = Router()


@router.message(Command("reset"))
@router.message(F.text == BTN_RESET)
async def reset_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ResetStates.waiting_confirmation)
    await message.answer(
        "Это удалит ваши данные в боте.\n"
        "Если вы owner — будет очищена вся семейная таблица и данные семьи.\n\n"
        "Продолжить?",
        reply_markup=confirm_keyboard("reset_confirm_yes", "reset_confirm_no"),
    )


@router.callback_query(ResetStates.waiting_confirmation, F.data == "reset_confirm_no")
async def reset_cancel(callback: CallbackQuery, state: FSMContext, services: AppServices) -> None:
    if not callback.from_user or not callback.message:
        return
    await state.clear()
    family = await services.family.get_actor_family(callback.from_user.id)
    if family:
        await callback.message.answer("Сброс отменен.", reply_markup=main_menu_keyboard())
    else:
        await state.set_state(OnboardingStates.waiting_setup_mode)
        await callback.message.answer("Сброс отменен.", reply_markup=onboarding_mode_keyboard())
    await callback.answer()


@router.callback_query(ResetStates.waiting_confirmation, F.data == "reset_confirm_yes")
async def reset_confirm(callback: CallbackQuery, state: FSMContext, services: AppServices) -> None:
    if not callback.from_user or not callback.message:
        return

    key = sha256_hex(f"{callback.from_user.id}|reset_user|{callback.id}")
    locked = await services.idempotency.check_and_lock(
        scope="reset_user",
        actor_id=callback.from_user.id,
        key=key,
        ttl_sec=600,
    )
    if not locked:
        await state.clear()
        await callback.message.answer("Сброс уже был выполнен.")
        await callback.answer()
        return

    result = await services.reset.reset_user(actor_id=callback.from_user.id)
    await state.clear()
    await state.set_state(OnboardingStates.waiting_setup_mode)
    if result.mode == "owner_wipe":
        await callback.message.answer(
            "Вы удалены из бота. Семейные данные очищены.",
            reply_markup=onboarding_mode_keyboard(),
        )
    elif result.mode == "member_leave":
        await callback.message.answer(
            "Вы удалены из семейной таблицы и ваши данные очищены.",
            reply_markup=onboarding_mode_keyboard(),
        )
    else:
        await callback.message.answer(
            "Локальные данные аккаунта удалены.",
            reply_markup=onboarding_mode_keyboard(),
        )
    await callback.answer()
