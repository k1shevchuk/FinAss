from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def report_period_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Неделя", callback_data="report:week")
    builder.button(text="Месяц", callback_data="report:month")
    builder.button(text="Год", callback_data="report:year")
    builder.adjust(3)
    return builder.as_markup()
