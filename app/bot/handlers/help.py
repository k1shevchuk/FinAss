from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.keyboards.menu import BTN_HELP, main_menu_keyboard, onboarding_mode_keyboard
from app.domain.services.container import AppServices

router = Router()


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def help_command(message: Message, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    actor_family = await services.family.get_actor_family(user.id)
    reply_markup = main_menu_keyboard() if actor_family else onboarding_mode_keyboard()

    await message.answer(
        "Что умеет бот:\n"
        "• Добавлять расход вручную\n"
        "• Сканировать чек по QR (fallback, если нет внешнего провайдера)\n"
        "• Делать отчеты по периодам\n"
        "• Вести балансы (основной/накопительный)\n"
        "• Вести общую семейную таблицу\n\n"
        "• Сбрасывать аккаунт и данные кнопкой «Сброс»\n\n"
        "• Перезапускать текущую сессию кнопкой «Перезапуск» или командой /restart\n\n"
        "Перед подключением Google Таблицы добавьте Editor-доступ для:\n"
        "hydra-950@finassbobot.iam.gserviceaccount.com\n\n"
        "Используйте кнопки внизу экрана. Команды вводить не обязательно.",
        reply_markup=reply_markup,
    )
