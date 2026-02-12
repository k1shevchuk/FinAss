from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Document, InlineKeyboardMarkup, Message, PhotoSize
from aiogram.utils.keyboard import InlineKeyboardBuilder
from structlog.stdlib import get_logger

from app.bot.keyboards.add_flow import category_keyboard, category_suggestion_keyboard
from app.bot.keyboards.common import confirm_keyboard
from app.bot.keyboards.menu import BTN_SCAN, main_menu_keyboard, onboarding_mode_keyboard
from app.bot.states.scan_receipt import ScanReceiptStates
from app.domain.entities import ReceiptItem, TelegramPhotoMeta
from app.domain.services.container import AppServices
from app.infra.receipt.qr_decode import QrDecodeError
from app.utils.idempotency import sha256_hex
from app.utils.validation import parse_decimal

router = Router()
logger = get_logger(__name__)


def fallback_choice_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Записать одной суммой", callback_data="scan_fallback:one_sum")
    builder.button(text="Внести вручную позиции", callback_data="scan_fallback:manual")
    builder.adjust(1)
    return builder.as_markup()


def _is_image_document(document: Document | None) -> bool:
    if document is None:
        return False
    mime = (document.mime_type or "").lower()
    if mime.startswith("image/"):
        return True
    file_name = (document.file_name or "").lower()
    return file_name.endswith(
        (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".heic", ".heif")
    )


def _photo_candidates(photos: list[PhotoSize], limit: int = 3) -> list[TelegramPhotoMeta]:
    # Telegram sends multiple resolutions for the same image. Try several from larger to smaller,
    # because the largest one can be temporarily unavailable right after upload.
    out: list[TelegramPhotoMeta] = []
    for item in reversed(photos):
        out.append(
            TelegramPhotoMeta(
                file_id=item.file_id,
                file_unique_id=item.file_unique_id,
                file_size=item.file_size,
            )
        )
        if len(out) >= limit:
            break
    return out


@router.message(Command("scan"))
@router.message(F.text == BTN_SCAN)
async def scan_start(message: Message, state: FSMContext) -> None:
    await state.set_state(ScanReceiptStates.waiting_photo)
    await message.answer(
        "Пришлите фото чека с QR-кодом.\n"
        "Можно отправить и как файл (документ), так часто лучше читается QR."
    )


@router.message(ScanReceiptStates.waiting_photo, F.photo)
@router.message(ScanReceiptStates.waiting_photo, F.document)
async def scan_receive_photo(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    actor_family = await services.family.get_actor_family(user.id)
    if not actor_family:
        await message.answer(
            "Сначала подключите Google Таблицу в онбординге.",
            reply_markup=onboarding_mode_keyboard(),
        )
        await state.clear()
        return

    candidates: list[TelegramPhotoMeta]
    if message.photo:
        candidates = _photo_candidates(message.photo)
    elif message.document:
        document = message.document
        if document is None:
            await message.answer("Не удалось прочитать файл. Отправьте изображение еще раз.")
            return
        candidates = [
            TelegramPhotoMeta(
                file_id=document.file_id,
                file_unique_id=document.file_unique_id,
                file_size=document.file_size,
            )
        ]
        if not _is_image_document(document):
            logger.info(
                "scan.document.non_image_mime_fallback",
                telegram_id=user.id,
                mime_type=document.mime_type,
                file_name=document.file_name,
            )
    else:
        await message.answer(
            "Нужен файл изображения: фото, PNG/JPG документ или скриншот QR."
        )
        return

    result = None
    saw_qr_decode_error = False
    download_error_message: str | None = None
    for candidate in candidates:
        try:
            result = await services.receipt.process_photo(
                actor_telegram_id=user.id,
                actor_name=user.full_name or str(user.id),
                file_meta=candidate,
            )
            break
        except QrDecodeError:
            saw_qr_decode_error = True
            continue
        except ValueError as exc:
            exc_text = str(exc)
            if "Не удалось получить фото из Telegram" in exc_text or "Не удалось скачать изображение" in exc_text:
                download_error_message = exc_text
                continue
            await message.answer(exc_text)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "scan.receive_photo.unexpected_error",
                telegram_id=user.id,
                error=str(exc),
            )
            await message.answer(
                "Не удалось обработать фото прямо сейчас. Попробуйте еще раз через несколько секунд."
            )
            return

    if result is None:
        if saw_qr_decode_error:
            await message.answer(
                "Не удалось найти QR-код. "
                "Сделайте фото ближе и резче, или отправьте изображение как файл (без сжатия)."
            )
            return
        if download_error_message:
            await message.answer(download_error_message)
            return
        await message.answer("Не удалось обработать изображение. Попробуйте отправить другое фото.")
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

    if result.items:
        normalized_items = await _normalize_receipt_items(
            items=result.items,
            categories=available_categories,
            services=services,
            actor_id=user.id,
        )
        total_from_items = sum((item.total_price for item in normalized_items), start=Decimal("0"))
        await state.update_data(
            receipt_items=_serialize_receipt_items(normalized_items),
            total=f"{total_from_items:.2f}",
        )
        await state.set_state(ScanReceiptStates.confirm_items)
        await message.answer(
            "Чек распознан. Позиции получены автоматически.\n"
            f"Найдено позиций: {len(normalized_items)}\n"
            f"Сумма: {total_from_items:.2f}\n\n"
            f"{_format_items_preview(normalized_items)}\n\n"
            "Записать эти позиции в таблицу?",
            reply_markup=confirm_keyboard("scan_items_confirm_yes", "scan_items_confirm_no"),
        )
        return

    await state.set_state(ScanReceiptStates.waiting_fallback_choice)
    total_label = (
        result.receipt_ref.total if result.receipt_ref.total is not None else "не определена"
    )
    await message.answer(
        "Чек распознан.\n"
        f"Payload: {result.payload_preview}\n"
        f"Сумма: {total_label}\n\n"
        "Автоматически получить товарные позиции не удалось. Выберите сценарий:",
        reply_markup=fallback_choice_keyboard(),
    )


@router.message(ScanReceiptStates.waiting_photo)
async def scan_waiting_photo_invalid(message: Message) -> None:
    await message.answer(
        "Пришлите изображение чека с QR-кодом (фото или image-документ) или нажмите «Отмена»."
    )


@router.callback_query(
    ScanReceiptStates.waiting_fallback_choice, F.data.startswith("scan_fallback:")
)
async def scan_choose_fallback(
    callback: CallbackQuery, state: FSMContext, services: AppServices
) -> None:
    if not isinstance(callback.message, Message) or callback.data is None or not callback.from_user:
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
            await _ask_scan_category(
                message=callback.message,
                state=state,
                services=services,
                actor_id=callback.from_user.id,
            )
        else:
            await state.set_state(ScanReceiptStates.waiting_fallback_total)
            await callback.message.answer("Введите итоговую сумму по чеку:")
    await callback.answer()


@router.message(ScanReceiptStates.waiting_fallback_item_name, F.text)
async def scan_fallback_item_name(
    message: Message, state: FSMContext, services: AppServices
) -> None:
    if message.text is None or not message.from_user:
        return
    await state.update_data(item_name=message.text.strip())
    data = await state.get_data()
    if data.get("total"):
        await state.set_state(ScanReceiptStates.waiting_fallback_category)
        await _ask_scan_category(
            message=message,
            state=state,
            services=services,
            actor_id=message.from_user.id,
        )
    else:
        await state.set_state(ScanReceiptStates.waiting_fallback_total)
        await message.answer("Введите итоговую сумму:")


@router.message(ScanReceiptStates.waiting_fallback_total, F.text)
async def scan_fallback_total(message: Message, state: FSMContext, services: AppServices) -> None:
    if message.text is None or not message.from_user:
        return
    try:
        total = parse_decimal(message.text)
    except ValueError:
        await message.answer("Некорректная сумма. Пример: 1299.50")
        return
    await state.update_data(total=str(total))
    await state.set_state(ScanReceiptStates.waiting_fallback_category)
    await _ask_scan_category(
        message=message,
        state=state,
        services=services,
        actor_id=message.from_user.id,
    )


@router.callback_query(ScanReceiptStates.waiting_fallback_category, F.data == "scan_cat_auto_yes")
async def scan_fallback_category_accept(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    data = await state.get_data()
    category = str(data.get("suggested_category", "")).strip()
    if not category:
        await callback.message.answer(
            "Выберите категорию:",
            reply_markup=category_keyboard(
                data.get("categories", []),
                page=0,
                select_prefix="scan_category",
                page_prefix="scan_cat_page",
            ),
        )
        await callback.answer()
        return
    await state.update_data(category=category)
    await _send_scan_summary(callback.message, state, category)
    await callback.answer()


@router.callback_query(ScanReceiptStates.waiting_fallback_category, F.data == "scan_cat_auto_no")
async def scan_fallback_category_reject(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message):
        return
    data = await state.get_data()
    await callback.message.answer(
        "Выберите категорию:",
        reply_markup=category_keyboard(
            data.get("categories", []),
            page=0,
            select_prefix="scan_category",
            page_prefix="scan_cat_page",
        ),
    )
    await callback.answer()


@router.callback_query(ScanReceiptStates.waiting_fallback_category, F.data.startswith("scan_cat_page:"))
async def scan_fallback_category_page(callback: CallbackQuery, state: FSMContext) -> None:
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
    await callback.message.edit_reply_markup(
        reply_markup=category_keyboard(
            categories,
            page=page,
            select_prefix="scan_category",
            page_prefix="scan_cat_page",
        )
    )
    await callback.answer()


@router.callback_query(ScanReceiptStates.waiting_fallback_category, F.data.startswith("scan_category:"))
async def scan_fallback_category(callback: CallbackQuery, state: FSMContext) -> None:
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
    await _send_scan_summary(callback.message, state, category)
    await callback.answer()


@router.callback_query(ScanReceiptStates.waiting_fallback_category, F.data.startswith("category:"))
async def scan_fallback_category_legacy(callback: CallbackQuery, state: FSMContext) -> None:
    if not isinstance(callback.message, Message) or callback.data is None:
        return
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await _send_scan_summary(callback.message, state, category)
    await callback.answer()


@router.callback_query(ScanReceiptStates.confirm_items, F.data == "scan_items_confirm_no")
async def scan_items_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Сканирование отменено.", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(ScanReceiptStates.confirm_items, F.data == "scan_items_confirm_yes")
async def scan_items_confirm(
    callback: CallbackQuery, state: FSMContext, services: AppServices
) -> None:
    if not callback.message or not callback.from_user:
        return
    idempotency_key = sha256_hex(f"{callback.from_user.id}|scan_items_submit|{callback.id}")
    locked = await services.idempotency.check_and_lock(
        scope="scan_items_submit",
        actor_id=callback.from_user.id,
        key=idempotency_key,
        ttl_sec=3600,
    )
    if not locked:
        await state.clear()
        await callback.message.answer("Этот чек уже был подтвержден ранее.")
        await callback.answer()
        return

    data = await state.get_data()
    actor_family = await services.family.get_actor_family(callback.from_user.id)
    if not actor_family:
        await callback.message.answer(
            "Семья не найдена. Подключите таблицу в онбординге.",
            reply_markup=onboarding_mode_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return
    _, sheet_id, _, _, family_currency = actor_family
    items = _deserialize_receipt_items(data.get("receipt_items"))
    if not items:
        await state.clear()
        await callback.message.answer(
            "Не удалось восстановить позиции чека. Попробуйте отправить фото снова."
        )
        await callback.answer()
        return

    currency = data.get("currency") or family_currency
    total = sum((item.total_price for item in items), start=Decimal("0"))
    try:
        batch = await services.receipt.build_batch_from_items(
            actor_telegram_id=callback.from_user.id,
            actor_name=callback.from_user.full_name or str(callback.from_user.id),
            payload=data["receipt_payload"],
            items=items,
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
    await callback.message.answer(
        f"Чек добавлен: {len(items)} позиций, сумма {total:.2f} {currency}.",
        reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(ScanReceiptStates.confirm_fallback, F.data == "scan_confirm_no")
async def scan_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Сканирование отменено.", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(ScanReceiptStates.confirm_fallback, F.data == "scan_confirm_yes")
async def scan_confirm(callback: CallbackQuery, state: FSMContext, services: AppServices) -> None:
    if not callback.message or not callback.from_user:
        return
    idempotency_key = sha256_hex(f"{callback.from_user.id}|scan_fallback_submit|{callback.id}")
    locked = await services.idempotency.check_and_lock(
        scope="scan_fallback_submit",
        actor_id=callback.from_user.id,
        key=idempotency_key,
        ttl_sec=3600,
    )
    if not locked:
        await state.clear()
        await callback.message.answer("Этот чек уже был подтвержден ранее.")
        await callback.answer()
        return

    data = await state.get_data()
    actor_family = await services.family.get_actor_family(callback.from_user.id)
    if not actor_family:
        await callback.message.answer(
            "Семья не найдена. Подключите таблицу в онбординге.",
            reply_markup=onboarding_mode_keyboard(),
        )
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
    await callback.message.answer("Чек добавлен в таблицу.", reply_markup=main_menu_keyboard())
    await callback.answer()


async def _ask_scan_category(
    *,
    message: Message,
    state: FSMContext,
    services: AppServices,
    actor_id: int,
) -> None:
    data = await state.get_data()
    categories = data.get("categories", []) or ["Другое"]
    item_name = str(data.get("item_name", "Чек")).strip()
    merchant = str(data.get("merchant", "")).strip()
    suggestion_text = " ".join(part for part in [item_name, merchant] if part)
    suggested = await services.category_matcher.match(actor_id=actor_id, text=suggestion_text)
    if suggested and suggested in categories:
        await state.update_data(suggested_category=suggested)
        await message.answer(
            f"Автокатегория: {suggested}. Оставить?",
            reply_markup=category_suggestion_keyboard(
                accept_cb="scan_cat_auto_yes",
                choose_cb="scan_cat_auto_no",
            ),
        )
        return

    await message.answer(
        "Выберите категорию:",
        reply_markup=category_keyboard(
            categories,
            page=0,
            select_prefix="scan_category",
            page_prefix="scan_cat_page",
        ),
    )


async def _send_scan_summary(message: Message, state: FSMContext, category: str) -> None:
    data = await state.get_data()
    summary = (
        "Проверьте данные:\n"
        f"Расход: {data.get('item_name', 'Чек')}\n"
        f"Сумма: {data.get('total')}\n"
        f"Категория: {category}\n"
    )
    await state.set_state(ScanReceiptStates.confirm_fallback)
    await message.answer(
        summary,
        reply_markup=confirm_keyboard("scan_confirm_yes", "scan_confirm_no"),
    )


async def _normalize_receipt_items(
    *,
    items: list[ReceiptItem],
    categories: list[str],
    services: AppServices,
    actor_id: int,
) -> list[ReceiptItem]:
    normalized: list[ReceiptItem] = []
    fallback_category = "Другое" if "Другое" in categories else (categories[0] if categories else "Другое")
    for item in items:
        category = item.category if item.category in categories else None
        if not category:
            suggested = await services.category_matcher.match(actor_id=actor_id, text=item.name)
            if suggested and suggested in categories:
                category = suggested
        normalized.append(
            ReceiptItem(
                name=item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total_price=item.total_price,
                category=category or fallback_category,
            )
        )
    return normalized


def _serialize_receipt_items(items: list[ReceiptItem]) -> list[dict[str, str]]:
    return [
        {
            "name": item.name,
            "quantity": str(item.quantity),
            "unit_price": str(item.unit_price),
            "total_price": str(item.total_price),
            "category": item.category,
        }
        for item in items
    ]


def _deserialize_receipt_items(raw: object) -> list[ReceiptItem]:
    if not isinstance(raw, list):
        return []
    parsed: list[ReceiptItem] = []
    for value in raw:
        if not isinstance(value, dict):
            continue
        try:
            item = ReceiptItem(
                name=str(value.get("name", "")).strip(),
                quantity=Decimal(str(value.get("quantity", "1"))),
                unit_price=Decimal(str(value.get("unit_price", "0"))),
                total_price=Decimal(str(value.get("total_price", "0"))),
                category=str(value.get("category", "Другое")).strip() or "Другое",
            )
        except (ArithmeticError, TypeError, ValueError):
            continue
        if item.name and item.total_price > Decimal("0"):
            parsed.append(item)
    return parsed


def _format_items_preview(items: list[ReceiptItem], *, limit: int = 8) -> str:
    if not items:
        return "- Нет позиций"
    lines: list[str] = []
    for index, item in enumerate(items[:limit], start=1):
        lines.append(
            f"{index}. {item.name} - {item.quantity} x {item.unit_price} = {item.total_price} ({item.category})"
        )
    if len(items) > limit:
        lines.append(f"... и еще {len(items) - limit} поз.")
    return "\n".join(lines)
