from datetime import datetime
from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.add_flow import add_mode_keyboard, category_keyboard
from app.bot.keyboards.common import confirm_keyboard
from app.bot.states.add_expense import AddExpenseStates
from app.domain.services.container import AppServices
from app.utils.idempotency import sha256_hex
from app.utils.timezone import now_utc, to_local
from app.utils.validation import parse_decimal

router = Router()


@router.message(Command("add"))
async def add_start(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    actor_family = await services.family.get_actor_family(user.id)
    if not actor_family:
        await message.answer("Сначала выполните /start и подключите таблицу.")
        return
    _, _, _, family_tz, family_currency = actor_family
    categories = await services.categories.list_categories(user.id)
    await state.set_state(AddExpenseStates.choose_mode)
    await state.update_data(
        timezone=family_tz,
        currency=family_currency,
        categories=[c.category for c in categories if c.enabled],
    )
    await message.answer("Как добавить расход?", reply_markup=add_mode_keyboard())


@router.callback_query(AddExpenseStates.choose_mode, F.data.startswith("add_mode:"))
async def add_choose_mode(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or callback.data is None:
        return
    mode = callback.data.split(":")[1]
    await state.update_data(mode=mode)
    if mode == "sum":
        await state.update_data(item_name="Расход", quantity="1")
        await state.set_state(AddExpenseStates.waiting_unit_price)
        await callback.message.answer("Введите сумму расхода:")
    else:
        await state.set_state(AddExpenseStates.waiting_item_name)
        await callback.message.answer("Введите название товара/расхода:")
    await callback.answer()


@router.message(AddExpenseStates.waiting_item_name, F.text)
async def add_item_name(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    await state.update_data(item_name=message.text.strip())
    await state.set_state(AddExpenseStates.waiting_quantity)
    await message.answer("Количество (например, 1 или 2.5):")


@router.message(AddExpenseStates.waiting_quantity, F.text)
async def add_quantity(message: Message, state: FSMContext) -> None:
    if message.text is None:
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
async def add_price(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        unit_price = parse_decimal(message.text)
    except ValueError:
        await message.answer("Некорректная цена. Пример: 159.90")
        return
    await state.update_data(unit_price=str(unit_price))
    data = await state.get_data()
    categories = data.get("categories", [])
    if categories:
        await state.set_state(AddExpenseStates.waiting_category)
        await message.answer("Выберите категорию:", reply_markup=category_keyboard(categories))
        return
    await state.update_data(category="Другое")
    await state.set_state(AddExpenseStates.waiting_datetime)
    await message.answer("Дата и время (`YYYY-MM-DD HH:MM`) или `now`.", parse_mode="Markdown")


@router.callback_query(AddExpenseStates.waiting_category, F.data.startswith("category:"))
async def add_category_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or callback.data is None:
        return
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await state.set_state(AddExpenseStates.waiting_datetime)
    await callback.message.answer(
        "Дата и время (`YYYY-MM-DD HH:MM`) или `now`.", parse_mode="Markdown"
    )
    await callback.answer()


@router.message(AddExpenseStates.waiting_datetime, F.text)
async def add_datetime(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    text = message.text.strip().lower()
    data = await state.get_data()
    timezone = data["timezone"]
    if text in {"", "now", "сейчас"}:
        local_dt = to_local(now_utc(), timezone)
    else:
        try:
            local_dt = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            await message.answer(
                "Неверный формат. Используйте `YYYY-MM-DD HH:MM` или `now`.", parse_mode="Markdown"
            )
            return
    await state.update_data(local_dt=local_dt.isoformat())
    await state.set_state(AddExpenseStates.waiting_merchant)
    await message.answer("Магазин (или `-`):", parse_mode="Markdown")


@router.message(AddExpenseStates.waiting_merchant, F.text)
async def add_merchant(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    merchant = message.text.strip()
    await state.update_data(merchant=None if merchant == "-" else merchant)
    await state.set_state(AddExpenseStates.waiting_notes)
    await message.answer("Комментарий (или `-`):", parse_mode="Markdown")


@router.message(AddExpenseStates.waiting_notes, F.text)
async def add_notes(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    notes = message.text.strip()
    await state.update_data(notes=None if notes == "-" else notes)
    data = await state.get_data()
    quantity = Decimal(data["quantity"])
    unit_price = Decimal(data["unit_price"])
    total = quantity * unit_price
    summary = (
        "Проверьте расход:\n"
        f"Товар: {data['item_name']}\n"
        f"Кол-во: {quantity}\n"
        f"Цена: {unit_price}\n"
        f"Итого: {total}\n"
        f"Категория: {data['category']}\n"
        f"Дата: {data['local_dt']}\n"
    )
    await state.set_state(AddExpenseStates.confirm)
    await message.answer(
        summary, reply_markup=confirm_keyboard("add_confirm_yes", "add_confirm_no")
    )


@router.callback_query(AddExpenseStates.confirm, F.data == "add_confirm_no")
async def add_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Добавление расхода отменено.")
    await callback.answer()


@router.callback_query(AddExpenseStates.confirm, F.data == "add_confirm_yes")
async def add_confirm(callback: CallbackQuery, state: FSMContext, services: AppServices) -> None:
    if not callback.message or not callback.from_user:
        return
    data = await state.get_data()
    key_raw = "|".join(
        [
            str(callback.from_user.id),
            data["item_name"],
            data["quantity"],
            data["unit_price"],
            data["local_dt"],
            data["category"],
        ]
    )
    key = sha256_hex(key_raw)
    locked = await services.idempotency.check_and_lock(
        scope="manual_expense",
        actor_id=callback.from_user.id,
        key=key,
        ttl_sec=3600,
    )
    if not locked:
        await callback.message.answer("Похоже, такой расход уже был отправлен недавно.")
        await callback.answer()
        await state.clear()
        return

    await services.expense.add_manual_expense(
        actor_telegram_id=callback.from_user.id,
        actor_name=callback.from_user.full_name or str(callback.from_user.id),
        item_name=data["item_name"],
        quantity=Decimal(data["quantity"]),
        unit_price=Decimal(data["unit_price"]),
        category=data["category"],
        currency=data["currency"],
        timezone=data["timezone"],
        merchant=data.get("merchant"),
        notes=data.get("notes"),
        local_dt=datetime.fromisoformat(data["local_dt"]),
    )
    await state.clear()
    await callback.message.answer("Расход добавлен. Спасибо.")
    await callback.answer()
