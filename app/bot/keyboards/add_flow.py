from math import ceil

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

CATEGORY_PAGE_SIZE = 12


def add_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Позиция (товар)", callback_data="add_mode:item")
    builder.button(text="Одной суммой", callback_data="add_mode:sum")
    builder.adjust(1)
    return builder.as_markup()


def category_keyboard(
    categories: list[str],
    *,
    page: int = 0,
    select_prefix: str,
    page_prefix: str,
) -> InlineKeyboardMarkup:
    prepared = categories or ["Другое"]
    total_pages = max(1, ceil(len(prepared) / CATEGORY_PAGE_SIZE))
    safe_page = min(max(page, 0), total_pages - 1)
    start = safe_page * CATEGORY_PAGE_SIZE
    end = start + CATEGORY_PAGE_SIZE

    builder = InlineKeyboardBuilder()
    for index in range(start, min(end, len(prepared))):
        category = prepared[index]
        label = category if len(category) <= 40 else f"{category[:37]}..."
        builder.button(text=label, callback_data=f"{select_prefix}:{index}")

    if total_pages > 1:
        if safe_page > 0:
            builder.button(text="⬅️", callback_data=f"{page_prefix}:{safe_page - 1}")
        builder.button(text=f"{safe_page + 1}/{total_pages}", callback_data=f"{page_prefix}:{safe_page}")
        if safe_page < total_pages - 1:
            builder.button(text="➡️", callback_data=f"{page_prefix}:{safe_page + 1}")

    builder.adjust(2, 2, 2, 2, 2, 2, 3)
    return builder.as_markup()


def category_suggestion_keyboard(*, accept_cb: str, choose_cb: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Оставить", callback_data=accept_cb)
    builder.button(text="📝 Выбрать вручную", callback_data=choose_cb)
    builder.adjust(1)
    return builder.as_markup()


def add_continue_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить ещё", callback_data="add_more")
    builder.button(text="✅ Завершить", callback_data="add_finish")
    builder.adjust(2)
    return builder.as_markup()


def add_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data="add_confirm_yes")
    builder.button(text="💰 Списать из накоплений", callback_data="add_confirm_savings")
    builder.button(text="✖️ Отмена", callback_data="add_confirm_no")
    builder.adjust(1)
    return builder.as_markup()
