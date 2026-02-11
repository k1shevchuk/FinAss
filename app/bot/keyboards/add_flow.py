from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def add_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Позиция (товар)", callback_data="add_mode:item")
    builder.button(text="Одной суммой", callback_data="add_mode:sum")
    builder.adjust(1)
    return builder.as_markup()


def category_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories[:20]:
        builder.button(text=category, callback_data=f"category:{category}")
    builder.adjust(2)
    return builder.as_markup()
