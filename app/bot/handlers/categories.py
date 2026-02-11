from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.domain.services.container import AppServices

router = Router()


@router.message(Command("categories"))
async def categories_command(message: Message, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    text = (message.text or "").strip()
    tokens = text.split(maxsplit=2)
    if len(tokens) == 1:
        categories = await services.categories.list_categories(user.id)
        if not categories:
            await message.answer("Категории не найдены. Выполните /start.")
            return
        lines = ["Категории:"]
        for c in categories:
            status = "on" if c.enabled else "off"
            lines.append(f"- {c.category} [{status}] ({', '.join(c.keywords)})")
        lines.append("")
        lines.append("Управление:")
        lines.append("/categories add <Название> | <kw1,kw2>")
        lines.append("/categories enable <Название>")
        lines.append("/categories disable <Название>")
        await message.answer("\n".join(lines))
        return

    action = tokens[1].lower()
    if action == "add":
        payload = tokens[2] if len(tokens) > 2 else ""
        if "|" not in payload:
            await message.answer("Формат: /categories add Продукты | молоко,хлеб")
            return
        category_name, keywords_raw = [x.strip() for x in payload.split("|", maxsplit=1)]
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        await services.categories.add_category(user.id, category_name, keywords)
        await message.answer(f"Категория '{category_name}' добавлена.")
        return

    if action in {"enable", "disable"}:
        if len(tokens) < 3:
            await message.answer(f"Формат: /categories {action} <Название>")
            return
        category_name = tokens[2].strip()
        updated = await services.categories.set_category_enabled(
            user.id, category_name, enabled=(action == "enable")
        )
        if not updated:
            await message.answer("Категория не найдена.")
            return
        await message.answer(f"Категория '{category_name}' обновлена.")
        return

    await message.answer("Неизвестная операция. Используйте /categories без аргументов.")
