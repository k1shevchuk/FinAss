from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.add_flow import category_keyboard
from app.bot.keyboards.common import confirm_keyboard
from app.bot.states.scan_receipt import ScanReceiptStates
from app.domain.entities import TelegramPhotoMeta
from app.domain.services.container import AppServices
from app.infra.receipt.qr_decode import QrDecodeError
from app.utils.validation import parse_decimal

router = Router()


def fallback_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Записать одной суммой", callback_data="scan_fallback:one_sum")
    builder.button(text="Внести вручную позиции", callback_data="scan_fallback:manual")
    builder.adjust(1)
    return builder.as_markup()


@router.message(Command("scan"))
async def scan_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ScanReceiptStates.waiting_photo)
    await message.answer("Пришлите фото чека с QR-кодом.")


@router.message(ScanReceiptStates.waiting_photo, F.photo)
async def scan_receive_photo(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user or not message.photo:
        return
    actor_family = await services.family.get_actor_family(user.id)
    if not actor_family:
        await message.answer("Сначала выполните /start и подключите таблицу.")
        await state.clear()
        return

    largest_photo = message.photo[-1]
    meta = TelegramPhotoMeta(
        file_id=largest_photo.file_id,
        file_unique_id=largest_photo.file_unique_id,
        file_size=largest_photo.file_size,
    )
    try:
        result = await services.receipt.process_photo(
            actor_telegram_id=user.id,
            actor_name=user.full_name or str(user.id),
            file_meta=meta,
        )
    except QrDecodeError:
        await message.answer("QR не найден. Попробуйте фото с лучшим освещением и резкостью.")
        return
    except ValueError as exc:
        await message.answer(str(exc))
        return

    categories = await services.categories.list_categories(user.id)
    available_categories = [c.category for c in categories if c.enabled] or ["Другое"]
    await state.update_data(
        receipt_payload=result.receipt_ref.raw_payload,
        payload_hash=result.payload_hash,
        payload_preview=result.payload_preview,
        total=str(result.receipt_ref.total) if result.receipt_ref.total is not None else "",
        merchant=result.receipt_ref.merchant or "",
        currency=result.receipt_ref.currency or "",
        categories=available_categories,
    )
    await state.set_state(ScanReceiptStates.waiting_fallback_choice)
    total_label = (
        result.receipt_ref.total if result.receipt_ref.total is not None else "не определена"
    )
    await message.answer(
        "Чек распознан.\n"
        f"Payload: {result.payload_preview}\n"
        f"Сумма: {total_label}\n\n"
        "Провайдер товаров не настроен. Выберите сценарий:",
        reply_markup=fallback_choice_keyboard(),
    )


@router.callback_query(
    ScanReceiptStates.waiting_fallback_choice, F.data.startswith("scan_fallback:")
)
async def scan_choose_fallback(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or callback.data is None:
        return
    mode = callback.data.split(":", 1)[1]
    await state.update_data(mode=mode)
    data = await state.get_data()
    if mode == "manual":
        await state.set_state(ScanReceiptStates.waiting_fallback_item_name)
        await callback.message.answer("Введите название расхода (например, 'Чек Магнит').")
    else:
        await state.update_data(item_name="Чек")
        if data.get("total"):
            await state.set_state(ScanReceiptStates.waiting_fallback_category)
            await callback.message.answer(
                "Выберите категорию:",
                reply_markup=category_keyboard(data["categories"]),
            )
        else:
            await state.set_state(ScanReceiptStates.waiting_fallback_total)
            await callback.message.answer("Введите итоговую сумму по чеку:")
    await callback.answer()


@router.message(ScanReceiptStates.waiting_fallback_item_name, F.text)
async def scan_fallback_item_name(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    await state.update_data(item_name=message.text.strip())
    data = await state.get_data()
    if data.get("total"):
        await state.set_state(ScanReceiptStates.waiting_fallback_category)
        await message.answer(
            "Выберите категорию:", reply_markup=category_keyboard(data["categories"])
        )
    else:
        await state.set_state(ScanReceiptStates.waiting_fallback_total)
        await message.answer("Введите итоговую сумму:")


@router.message(ScanReceiptStates.waiting_fallback_total, F.text)
async def scan_fallback_total(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    try:
        total = parse_decimal(message.text)
    except ValueError:
        await message.answer("Некорректная сумма. Пример: 1299.50")
        return
    await state.update_data(total=str(total))
    data = await state.get_data()
    await state.set_state(ScanReceiptStates.waiting_fallback_category)
    await message.answer("Выберите категорию:", reply_markup=category_keyboard(data["categories"]))


@router.callback_query(ScanReceiptStates.waiting_fallback_category, F.data.startswith("category:"))
async def scan_fallback_category(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.message or callback.data is None:
        return
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    data = await state.get_data()
    summary = (
        "Проверьте данные:\n"
        f"Расход: {data.get('item_name', 'Чек')}\n"
        f"Сумма: {data.get('total')}\n"
        f"Категория: {category}\n"
    )
    await state.set_state(ScanReceiptStates.confirm_fallback)
    await callback.message.answer(
        summary,
        reply_markup=confirm_keyboard("scan_confirm_yes", "scan_confirm_no"),
    )
    await callback.answer()


@router.callback_query(ScanReceiptStates.confirm_fallback, F.data == "scan_confirm_no")
async def scan_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Сканирование отменено.")
    await callback.answer()


@router.callback_query(ScanReceiptStates.confirm_fallback, F.data == "scan_confirm_yes")
async def scan_confirm(callback: CallbackQuery, state: FSMContext, services: AppServices) -> None:
    if not callback.message or not callback.from_user:
        return
    data = await state.get_data()
    actor_family = await services.family.get_actor_family(callback.from_user.id)
    if not actor_family:
        await callback.message.answer("Семья не найдена. Выполните /start.")
        await state.clear()
        await callback.answer()
        return
    _, sheet_id, _, _, family_currency = actor_family

    total = Decimal(str(data["total"]))
    currency = data.get("currency") or family_currency
    try:
        batch = await services.receipt.build_batch_from_fallback(
            actor_telegram_id=callback.from_user.id,
            actor_name=callback.from_user.full_name or str(callback.from_user.id),
            payload=data["receipt_payload"],
            item_name=data.get("item_name", "Чек"),
            total=total,
            category=data["category"],
            currency=currency,
            merchant=data.get("merchant") or None,
            notes=f"QR:{data.get('payload_preview', '')}",
        )
    except ValueError as exc:
        await callback.message.answer(str(exc))
        await state.clear()
        await callback.answer()
        return

    await services.expense.add_expense_batch(batch=batch, sheet_id=sheet_id)
    if batch.receipt_hash:
        await services.receipt.mark_processed(
            actor_telegram_id=callback.from_user.id,
            receipt_hash=batch.receipt_hash,
            event_local_datetime=batch.local_datetime,
            total_price=total,
            currency=currency,
        )
    await state.clear()
    await callback.message.answer("Чек добавлен в таблицу.")
    await callback.answer()
