from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start — онбординг и создание таблицы\n"
        "/add — добавить трату\n"
        "/scan — отправить фото чека с QR\n"
        "/report — сводка за период\n"
        "/categories — категории\n"
        "/family — участники семьи\n"
        "/settings — валюта/таймзона/округление\n"
        "/cancel — отменить текущий сценарий"
    )
