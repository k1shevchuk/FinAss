from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def family_management_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Список участников", callback_data="family:list")
    builder.button(text="Создать инвайт", callback_data="family:invite")
    builder.button(text="Удалить участника", callback_data="family:remove")
    builder.adjust(1)
    return builder.as_markup()
