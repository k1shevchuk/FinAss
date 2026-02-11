from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def report_period_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="7 дней", callback_data="report:week")
    builder.button(text="30 дней", callback_data="report:30d")
    builder.button(text="Месяц", callback_data="report:month")
    builder.button(text="Год", callback_data="report:year")
    builder.button(text="Свой период", callback_data="report:custom")
    builder.adjust(2, 2, 1)
    return builder.as_markup()
