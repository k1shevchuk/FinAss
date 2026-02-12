from datetime import datetime
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.add_flow import (
    add_confirm_keyboard,
    add_continue_keyboard,
    add_mode_keyboard,
    category_keyboard,
    category_suggestion_keyboard,
)
from app.bot.keyboards.menu import BTN_ADD, main_menu_keyboard, onboarding_mode_keyboard
from app.bot.states.add_expense import AddExpenseStates
from app.domain.services.container import AppServices
from app.utils.idempotency import sha256_hex
from app.utils.timezone import now_utc, to_local
from app.utils.validation import parse_decimal

router = Router()


@router.message(Command("add"))
@router.message(F.text == BTN_ADD)
async def add_start(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return

    actor_family = await services.family.get_actor_family(user.id)
    if not actor_family:
        await message.answer(
            "Сначала подключите Google Таблицу в онбординге.",
            reply_markup=onboarding_mode_keyboard(),
        )
        return

    _, _, _, family_tz, family_currency = actor_family
    settings = await services.settings.get_settings(user.id)
    timezone = settings.get("timezone", family_tz)
    currency = settings.get("currency", family_currency)

    categories = await services.categories.list_categories(user.id)
    enabled_categories = [category.category for category in categories if category.enabled]
    await state.set_state(AddExpenseStates.choose_mode)
    await state.update_data(
        timezone=timezone,
        currency=currency,
        categories=enabled_categories or ["Другое"],
        category_page=0,
        added_count=0,
        added_total="0",
    )
    await message.answer("Как добавить расход?", reply_markup=add_mode_keyboard())


@router.callback_query(AddExpenseStates.choose_mode, F.data.startswith("add_mode:"))
async def add_choose_mode(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message) or callback.data is None:
        return

    mode = callback.data.split(":", maxsplit=1)[1]
    await state.update_data(mode=mode)
    await _start_new_item(callback.message, state)
    await callback.answer()


@router.message(AddExpenseStates.waiting_item_name, F.text)
async def add_item_name(message: Message, state: FSMContext) -> None:
    if not message.text:
        return

    await state.update_data(item_name=message.text.strip())
    await state.set_state(AddExpenseStates.waiting_quantity)
    await message.answer("Количество (например, 1 или 2.5):")


@router.message(AddExpenseStates.waiting_quantity, F.text)
async def add_quantity(message: Message, state: FSMContext) -> None:
    if not message.text:
        return

    try:
        quantity = parse_decimal(message.text)
    except ValueError:
        await message.answer("Некорректное количество. Пример: 1 или 0.5")
        return

    await state.update_data(quantity=str(quantity))
    await state.set_state(AddExpenseStates.waiting_unit_price)
    await message.answer("Цена за единицу:")


@router.message(AddExpenseStates.waiting_unit_price, F.text)
async def add_price(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    try:
        unit_price = parse_decimal(message.text)
    except ValueError:
        await message.answer("Некорректная цена. Пример: 159.90")
        return

    await state.update_data(unit_price=str(unit_price))
    data = await state.get_data()
    categories = data.get("categories", [])
    item_name = str(data.get("item_name", "")).strip()

    if not categories:
        await state.update_data(category="Другое")
        await _go_to_confirm(message, state)
        return

    suggested = await services.category_matcher.match(actor_id=user.id, text=item_name)
    if suggested and suggested in categories:
        await state.set_state(AddExpenseStates.waiting_category)
        await state.update_data(suggested_category=suggested)
        await message.answer(
            f"Автокатегория: {suggested}. Оставить?",
            reply_markup=category_suggestion_keyboard(
                accept_cb="add_cat_auto_yes",
                choose_cb="add_cat_auto_no",
            ),
        )
        return

    await state.set_state(AddExpenseStates.waiting_category)
    await message.answer(
        "Выберите категорию:",
        reply_markup=category_keyboard(
            categories,
            page=0,
            select_prefix="add_category",
            page_prefix="add_cat_page",
        ),
    )


@router.callback_query(AddExpenseStates.waiting_category, F.data == "add_cat_auto_yes")
async def add_auto_category_accept(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return

    data = await state.get_data()
    suggested = str(data.get("suggested_category", "")).strip()
    if not suggested:
        categories = data.get("categories", [])
        await callback.message.answer(
            "Выберите категорию:",
            reply_markup=category_keyboard(
                categories,
                page=0,
                select_prefix="add_category",
                page_prefix="add_cat_page",
            ),
        )
        await callback.answer()
        return

    await state.update_data(category=suggested)
    await _go_to_confirm(callback.message, state)
    await callback.answer()


@router.callback_query(AddExpenseStates.waiting_category, F.data == "add_cat_auto_no")
async def add_auto_category_reject(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    data = await state.get_data()
    categories = data.get("categories", [])
    await callback.message.answer(
        "Выберите категорию:",
        reply_markup=category_keyboard(
            categories,
            page=0,
            select_prefix="add_category",
            page_prefix="add_cat_page",
        ),
    )
    await callback.answer()


@router.callback_query(AddExpenseStates.waiting_category, F.data.startswith("add_cat_page:"))
async def add_category_page(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message) or callback.data is None:
        return
    data = await state.get_data()
    categories = data.get("categories", [])
    if not categories:
        await callback.answer("Категории не найдены", show_alert=True)
        return
    try:
        page = int(callback.data.split(":", 1)[1])
    except ValueError:
        page = 0
    await state.update_data(category_page=page)
    await callback.message.edit_reply_markup(
        reply_markup=category_keyboard(
            categories,
            page=page,
            select_prefix="add_category",
            page_prefix="add_cat_page",
        )
    )
    await callback.answer()


@router.callback_query(AddExpenseStates.waiting_category, F.data.startswith("add_category:"))
async def add_category_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message) or callback.data is None:
        return

    data = await state.get_data()
    categories = data.get("categories", [])
    try:
        index = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Ошибка категории", show_alert=True)
        return
    if index < 0 or index >= len(categories):
        await callback.answer("Категория недоступна", show_alert=True)
        return
    category = str(categories[index])
    await state.update_data(category=category)
    await _go_to_confirm(callback.message, state)
    await callback.answer()


@router.callback_query(AddExpenseStates.waiting_category, F.data.startswith("category:"))
async def add_category_legacy_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message) or callback.data is None:
        return
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await _go_to_confirm(callback.message, state)
    await callback.answer()


@router.callback_query(AddExpenseStates.confirm, F.data == "add_confirm_no")
async def add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer(
            "Добавление расхода отменено.", reply_markup=main_menu_keyboard()
        )
    await callback.answer()


@router.callback_query(AddExpenseStates.confirm, F.data == "add_confirm_yes")
async def add_confirm(callback: CallbackQuery, state: FSMContext, services: AppServices) -> None:
    if not isinstance(callback.message, Message) or not callback.from_user:
        return

    data = await state.get_data()
    idempotency_key = sha256_hex(f"{callback.from_user.id}|manual_add_submit|{callback.id}")
    locked = await services.idempotency.check_and_lock(
        scope="manual_expense_submit",
        actor_id=callback.from_user.id,
        key=idempotency_key,
        ttl_sec=3600,
    )
    if not locked:
        await callback.message.answer("Похоже, этот расход уже был обработан.")
        await state.clear()
        await callback.answer()
        return

    try:
        total, _ = await _persist_manual_item(
            state=state,
            services=services,
            actor_id=callback.from_user.id,
            actor_name=callback.from_user.full_name or str(callback.from_user.id),
            deduct_from_savings=False,
        )
    except ValueError as exc:
        await callback.message.answer(str(exc))
        await callback.answer()
        return
    await callback.message.answer(
        f"Позиция добавлена: {total:.2f} {data['currency']}",
        reply_markup=add_continue_keyboard(),
    )
    await callback.answer()


@router.callback_query(AddExpenseStates.confirm, F.data == "add_confirm_savings")
async def add_confirm_savings(
    callback: CallbackQuery, state: FSMContext, services: AppServices
) -> None:
    if not isinstance(callback.message, Message) or not callback.from_user:
        return

    data = await state.get_data()
    idempotency_key = sha256_hex(f"{callback.from_user.id}|manual_add_submit_savings|{callback.id}")
    locked = await services.idempotency.check_and_lock(
        scope="manual_expense_submit_savings",
        actor_id=callback.from_user.id,
        key=idempotency_key,
        ttl_sec=3600,
    )
    if not locked:
        await callback.message.answer("Похоже, этот расход уже был обработан.")
        await state.clear()
        await callback.answer()
        return

    try:
        total, _ = await _persist_manual_item(
            state=state,
            services=services,
            actor_id=callback.from_user.id,
            actor_name=callback.from_user.full_name or str(callback.from_user.id),
            deduct_from_savings=True,
        )
    except PermissionError:
        await callback.message.answer("Только owner может списывать из накоплений.")
        await callback.answer()
        return
    except ValueError as exc:
        await callback.message.answer(str(exc))
        await callback.answer()
        return

    await callback.message.answer(
        f"Позиция добавлена и списана из накоплений: {total:.2f} {data['currency']}",
        reply_markup=add_continue_keyboard(),
    )
    await callback.answer()


@router.callback_query(AddExpenseStates.waiting_continue_action, F.data == "add_more")
async def add_more(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    await _start_new_item(callback.message, state)
    await callback.answer()


@router.callback_query(AddExpenseStates.waiting_continue_action, F.data == "add_finish")
async def add_finish(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return

    data = await state.get_data()
    count = int(data.get("added_count", 0))
    total = Decimal(str(data.get("added_total", "0")))
    currency = str(data.get("currency", "RUB"))
    await state.clear()
    await callback.message.answer(
        f"Сессия добавления завершена.\nДобавлено позиций: {count}\nСумма: {total:.2f} {currency}",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


async def _start_new_item(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    mode = str(data.get("mode", "item"))
    await state.update_data(
        item_name="",
        quantity="",
        unit_price="",
        category="",
        suggested_category="",
        local_dt="",
    )
    if mode == "sum":
        await state.update_data(item_name="Расход", quantity="1")
        await state.set_state(AddExpenseStates.waiting_unit_price)
        await message.answer("Введите сумму расхода:")
        return

    await state.set_state(AddExpenseStates.waiting_item_name)
    await message.answer("Введите название товара/расхода:")


async def _go_to_confirm(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    timezone = str(data["timezone"])
    local_dt = to_local(now_utc(), timezone)

    quantity = Decimal(str(data["quantity"]))
    unit_price = Decimal(str(data["unit_price"]))
    total = quantity * unit_price

    await state.update_data(local_dt=local_dt.isoformat())
    summary = (
        "Проверьте расход:\n"
        f"Товар: {data['item_name']}\n"
        f"Кол-во: {quantity}\n"
        f"Цена: {unit_price}\n"
        f"Итого: {total}\n"
        f"Категория: {data['category']}\n"
        f"Время: {local_dt.isoformat(timespec='minutes')}"
    )
    await state.set_state(AddExpenseStates.confirm)
    await message.answer(
        summary,
        reply_markup=add_confirm_keyboard(),
    )


async def _persist_manual_item(
    *,
    state: FSMContext,
    services: AppServices,
    actor_id: int,
    actor_name: str,
    deduct_from_savings: bool,
) -> tuple[Decimal, str]:
    data = await state.get_data()
    quantity = Decimal(str(data["quantity"]))
    unit_price = Decimal(str(data["unit_price"]))
    total = quantity * unit_price
    currency = str(data["currency"])

    await services.expense.add_manual_expense(
        actor_telegram_id=actor_id,
        actor_name=actor_name,
        item_name=str(data["item_name"]),
        quantity=quantity,
        unit_price=unit_price,
        category=str(data["category"]),
        currency=currency,
        timezone=str(data["timezone"]),
        merchant=None,
        notes=None,
        local_dt=datetime.fromisoformat(str(data["local_dt"])),
    )

    if deduct_from_savings:
        await services.accounts.spend_from_savings(
            actor_id=actor_id,
            actor_name=actor_name,
            amount=total,
            note=f"expense:{data['item_name']}",
        )
    else:
        await services.accounts.spend_main_for_expense(
            actor_id=actor_id,
            actor_name=actor_name,
            amount=total,
            note=f"expense:{data['item_name']}",
        )

    added_count = int(data.get("added_count", 0)) + 1
    added_total = Decimal(str(data.get("added_total", "0"))) + total
    await state.update_data(added_count=added_count, added_total=str(added_total))
    await state.set_state(AddExpenseStates.waiting_continue_action)
    return total, currency
