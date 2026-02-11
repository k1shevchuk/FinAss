from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.domain.services.container import AppServices
from app.utils.validation import is_valid_telegram_username

router = Router()


@router.message(Command("family"))
async def family_command(message: Message, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    text = (message.text or "").strip()
    tokens = text.split(maxsplit=2)
    if len(tokens) == 1:
        members = await services.family.list_members(user.id)
        if not members:
            await message.answer("Семья не найдена. Выполните /start.")
            return
        lines = ["Участники семьи:"]
        lines.extend([f"- {member_id}: {role}" for member_id, role in members])
        lines.append("")
        lines.append("Команды:")
        lines.append("/family invite")
        lines.append("/family invite @username")
        lines.append("/family invite <telegram_id>")
        lines.append("/family remove <telegram_id>")
        await message.answer("\n".join(lines))
        return

    action = tokens[1].lower()
    if action == "invite":
        target_username: str | None = None
        target_telegram_id: int | None = None
        if len(tokens) > 2:
            target = tokens[2].strip()
            if target.startswith("@"):
                if not is_valid_telegram_username(target):
                    await message.answer("Некорректный username.")
                    return
                target_username = target
            else:
                try:
                    target_telegram_id = int(target)
                except ValueError:
                    await message.answer("Укажите @username или числовой telegram_id.")
                    return
        try:
            invite = await services.family.create_invite(
                owner_id=user.id,
                target_username=target_username,
                target_telegram_id=target_telegram_id,
            )
        except PermissionError:
            await message.answer("Только owner может создавать инвайты.")
            return
        except ValueError as exc:
            await message.answer(str(exc))
            return
        await message.answer(
            "Инвайт создан.\n"
            f"Код: `{invite.code}`\n"
            f"Действует до: {invite.expires_at_utc.isoformat()}\n"
            "Второй пользователь должен выполнить: /join <код>",
            parse_mode="Markdown",
        )
        return

    if action == "remove":
        if len(tokens) < 3:
            await message.answer("Формат: /family remove <telegram_id>")
            return
        try:
            member_id = int(tokens[2].strip())
        except ValueError:
            await message.answer("telegram_id должен быть числом.")
            return
        try:
            removed = await services.family.remove_member(
                owner_id=user.id, member_telegram_id=member_id
            )
        except PermissionError:
            await message.answer("Только owner может удалять участников.")
            return
        except ValueError as exc:
            await message.answer(str(exc))
            return
        if not removed:
            await message.answer("Участник не найден.")
            return
        await message.answer("Участник удален.")
        return

    await message.answer("Неизвестная операция. Используйте /family без аргументов.")


@router.message(Command("join"))
async def join_command(message: Message, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    text = (message.text or "").strip()
    tokens = text.split(maxsplit=1)
    if len(tokens) < 2:
        await message.answer("Формат: /join <код>")
        return
    code = tokens[1].strip()
    try:
        result = await services.family.join_by_code(actor_id=user.id, code=code)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await message.answer(
        "Вы подключены к семейной таблице.\n"
        f"family_id: {result.family_id}\n"
        f"role: {result.role.value}"
    )
