from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_ADD = "➕ Добавить расход"
BTN_SCAN = "🧾 Скан чека"
BTN_REPORT = "📊 Отчет"
BTN_CATEGORIES = "🏷 Категории"
BTN_FAMILY = "👨‍👩‍👧‍👦 Семья"
BTN_SETTINGS = "⚙️ Настройки"
BTN_HELP = "❓ Помощь"
BTN_MENU = "🏠 Меню"
BTN_CANCEL = "✖️ Отмена"

BTN_ONB_CREATE = "🆕 Создать таблицу"
BTN_ONB_ATTACH = "🔗 Подключить таблицу"


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ADD), KeyboardButton(text=BTN_SCAN)],
            [KeyboardButton(text=BTN_REPORT)],
            [KeyboardButton(text=BTN_CATEGORIES), KeyboardButton(text=BTN_FAMILY)],
            [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def onboarding_mode_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_ONB_CREATE)],
            [KeyboardButton(text=BTN_ONB_ATTACH)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)], [KeyboardButton(text=BTN_MENU)]],
        resize_keyboard=True,
        is_persistent=True,
    )

