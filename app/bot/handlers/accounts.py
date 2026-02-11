from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.menu import BTN_ACCOUNTS, main_menu_keyboard, onboarding_mode_keyboard
from app.bot.states.accounts import AccountsStates
from app.domain.services.container import AppServices
from app.utils.idempotency import sha256_hex
from app.utils.validation import parse_decimal

router = Router()


def _accounts_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬆️ Пополнить основной", callback_data="acc:topup")
    builder.button(text="🔁 В накопления", callback_data="acc:transfer")
    builder.button(text="➖ Списать из накоплений", callback_data="acc:spend_savings")
    builder.button(text="🔄 Обновить", callback_data="acc:refresh")
    builder.button(text="🏠 Меню", callback_data="acc:menu")
    builder.adjust(2, 1, 2)
    return builder.as_markup()


async def _send_accounts_panel(message: Message, services: AppServices, actor_id: int) -> None:
    actor_family = await services.family.get_actor_family(actor_id)
    if not actor_family:
        await message.answer(
            "Сначала подключите Google Таблицу в онбординге.",
            reply_markup=onboarding_mode_keyboard(),
        )
        return
    _, _, owner_id, _, _ = actor_family
    main_balance, savings_balance, currency = await services.accounts.get_balances(
        actor_id=actor_id
    )
    role_hint = "owner" if actor_id == owner_id else "editor"
    await message.answer(
        "Счета семьи:\n"
        f"• Основной: {main_balance:.2f} {currency}\n"
        f"• Накопительный: {savings_balance:.2f} {currency}\n"
        f"• Ваша роль: {role_hint}\n\n"
        "Для безопасности менять балансы может только owner.",
        reply_markup=_accounts_actions_keyboard(),
    )


@router.message(Command("accounts"))
@router.message(F.text == BTN_ACCOUNTS)
async def accounts_start(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    await state.clear()
    await _send_accounts_panel(message, services, user.id)


@router.callback_query(F.data == "acc:refresh")
async def accounts_refresh(
    callback: CallbackQuery, state: FSMContext, services: AppServices
) -> None:
    if not isinstance(callback.message, Message) or not callback.from_user:
        return
    await state.clear()
    await _send_accounts_panel(callback.message, services, callback.from_user.id)
    await callback.answer()


@router.callback_query(F.data == "acc:topup")
async def accounts_topup_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await callback.message.answer("Введите сумму пополнения основного счёта:")
    await state.set_state(AccountsStates.waiting_topup_amount)
    await callback.answer()


@router.callback_query(F.data == "acc:transfer")
async def accounts_transfer_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await callback.message.answer("Введите сумму перевода в накопления:")
    await state.set_state(AccountsStates.waiting_transfer_amount)
    await callback.answer()


@router.callback_query(F.data == "acc:spend_savings")
async def accounts_spend_savings_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await callback.message.answer("Введите сумму списания из накоплений:")
    await state.set_state(AccountsStates.waiting_spend_savings_amount)
    await callback.answer()


@router.callback_query(F.data == "acc:menu")
async def accounts_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.message(AccountsStates.waiting_topup_amount, F.text)
async def accounts_topup_apply(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user or not message.text:
        return
    try:
        amount = parse_decimal(message.text.strip())
    except ValueError:
        await message.answer("Некорректная сумма. Пример: 1000 или 1000.50")
        return

    key = sha256_hex(f"{user.id}|topup|{message.message_id}|{amount}")
    locked = await services.idempotency.check_and_lock(
        scope="accounts_topup",
        actor_id=user.id,
        key=key,
        ttl_sec=3600,
    )
    if not locked:
        await state.clear()
        await message.answer("Операция уже была обработана.", reply_markup=main_menu_keyboard())
        return

    try:
        await services.accounts.topup_main(
            actor_id=user.id,
            actor_name=user.full_name or str(user.id),
            amount=amount,
            note=None,
        )
    except PermissionError:
        await state.clear()
        await message.answer(
            "Только owner может менять балансы.", reply_markup=_accounts_actions_keyboard()
        )
        return
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    await message.answer("Основной счёт пополнен.")
    await _send_accounts_panel(message, services, user.id)


@router.message(AccountsStates.waiting_transfer_amount, F.text)
async def accounts_transfer_apply(
    message: Message, state: FSMContext, services: AppServices
) -> None:
    user = message.from_user
    if not user or not message.text:
        return
    try:
        amount = parse_decimal(message.text.strip())
    except ValueError:
        await message.answer("Некорректная сумма. Пример: 500 или 500.00")
        return

    key = sha256_hex(f"{user.id}|transfer|{message.message_id}|{amount}")
    locked = await services.idempotency.check_and_lock(
        scope="accounts_transfer",
        actor_id=user.id,
        key=key,
        ttl_sec=3600,
    )
    if not locked:
        await state.clear()
        await message.answer("Операция уже была обработана.", reply_markup=main_menu_keyboard())
        return

    try:
        await services.accounts.transfer_to_savings(
            actor_id=user.id,
            actor_name=user.full_name or str(user.id),
            amount=Decimal(str(amount)),
            note=None,
        )
    except PermissionError:
        await state.clear()
        await message.answer(
            "Только owner может менять балансы.", reply_markup=_accounts_actions_keyboard()
        )
        return
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    await message.answer("Средства переведены в накопления.")
    await _send_accounts_panel(message, services, user.id)


@router.message(AccountsStates.waiting_spend_savings_amount, F.text)
async def accounts_spend_savings_apply(
    message: Message, state: FSMContext, services: AppServices
) -> None:
    user = message.from_user
    if not user or not message.text:
        return
    try:
        amount = parse_decimal(message.text.strip())
    except ValueError:
        await message.answer("Некорректная сумма. Пример: 300 или 300.00")
        return

    key = sha256_hex(f"{user.id}|spend_savings|{message.message_id}|{amount}")
    locked = await services.idempotency.check_and_lock(
        scope="accounts_spend_savings",
        actor_id=user.id,
        key=key,
        ttl_sec=3600,
    )
    if not locked:
        await state.clear()
        await message.answer("Операция уже была обработана.", reply_markup=main_menu_keyboard())
        return

    try:
        await services.accounts.spend_from_savings(
            actor_id=user.id,
            actor_name=user.full_name or str(user.id),
            amount=Decimal(str(amount)),
            note=None,
        )
    except PermissionError:
        await state.clear()
        await message.answer(
            "Только owner может менять балансы.", reply_markup=_accounts_actions_keyboard()
        )
        return
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    await message.answer("Сумма списана из накоплений.")
    await _send_accounts_panel(message, services, user.id)
