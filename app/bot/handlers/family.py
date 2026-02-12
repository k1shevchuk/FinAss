from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.menu import BTN_FAMILY, main_menu_keyboard
from app.bot.states.family import FamilyStates
from app.domain.services.container import AppServices
from app.utils.validation import is_valid_telegram_username

router = Router()


def _role_label(role: str) -> str:
    if role == "owner":
        return "владелец"
    if role == "editor":
        return "участник"
    return role


def family_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать инвайт", callback_data="family:invite")
    builder.button(text="🗑 Удалить участника", callback_data="family:remove")
    builder.button(text="🔑 Ввести код", callback_data="family:join")
    builder.button(text="🔄 Обновить", callback_data="family:refresh")
    builder.button(text="🏠 Меню", callback_data="family:menu")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


async def _send_family_panel(message: Message, services: AppServices, actor_id: int) -> None:
    members = await services.family.list_members(actor_id)
    if not members:
        await message.answer(
            "Вы пока не состоите в семье. Если у вас есть код, нажмите «Ввести код».",
            reply_markup=family_actions_keyboard(),
        )
        return

    lines = ["Участники семьи:"]
    for member_id, role in members:
        lines.append(f"• {member_id}: {_role_label(role)}")
    lines.append("\nУправление через кнопки ниже.")
    await message.answer("\n".join(lines), reply_markup=family_actions_keyboard())


@router.message(Command("family"))
@router.message(F.text == BTN_FAMILY)
async def family_start(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    await state.clear()
    await _send_family_panel(message, services, user.id)


@router.callback_query(F.data == "family:refresh")
async def family_refresh(callback: CallbackQuery, state: FSMContext, services: AppServices) -> None:
    user = callback.from_user
    if not isinstance(callback.message, Message) or not user:
        return
    await state.clear()
    await _send_family_panel(callback.message, services, user.id)
    await callback.answer()


@router.callback_query(F.data == "family:invite")
async def family_invite_request(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FamilyStates.waiting_invite_target)
    if callback.message:
        await callback.message.answer(
            "Кого пригласить?\n"
            "Отправьте @username или telegram_id.\n"
            "Если нужен общий код без цели, отправьте «-»."
        )
    await callback.answer()


@router.callback_query(F.data == "family:remove")
async def family_remove_request(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FamilyStates.waiting_remove_member_id)
    if callback.message:
        await callback.message.answer("Введите telegram_id участника для удаления.")
    await callback.answer()


@router.callback_query(F.data == "family:join")
async def family_join_request(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FamilyStates.waiting_join_code)
    if callback.message:
        await callback.message.answer("Введите код приглашения.")
    await callback.answer()


@router.callback_query(F.data == "family:menu")
async def family_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.message(FamilyStates.waiting_invite_target, F.text)
async def family_invite_commit(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    target_username: str | None = None
    target_telegram_id: int | None = None
    target = message.text.strip()

    if target and target != "-":
        if target.startswith("@"):
            if not is_valid_telegram_username(target):
                await message.answer("Некорректный username. Пример: @username")
                return
            target_username = target
        else:
            try:
                target_telegram_id = int(target)
            except ValueError:
                await message.answer("Нужен @username, telegram_id или «-».")
                return

    try:
        invite = await services.family.create_invite(
            owner_id=user.id,
            target_username=target_username,
            target_telegram_id=target_telegram_id,
        )
    except PermissionError:
        await message.answer("Только владелец семьи может создавать инвайты.")
        return
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    await message.answer(
        "Инвайт создан.\n"
        f"Код: `{invite.code}`\n"
        f"Действует до: {invite.expires_at_utc.isoformat()}\n"
        "Передайте код участнику, он введет его через кнопку «Ввести код».",
        parse_mode="Markdown",
    )
    await _send_family_panel(message, services, user.id)


@router.message(FamilyStates.waiting_remove_member_id, F.text)
async def family_remove_commit(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    try:
        member_id = int(message.text.strip())
    except ValueError:
        await message.answer("telegram_id должен быть числом.")
        return

    try:
        removed = await services.family.remove_member(
            owner_id=user.id, member_telegram_id=member_id
        )
    except PermissionError:
        await message.answer("Только владелец семьи может удалять участников.")
        return
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    if removed:
        await message.answer("Участник удален.")
    else:
        await message.answer("Участник не найден.")
    await _send_family_panel(message, services, user.id)


@router.message(FamilyStates.waiting_join_code, F.text)
async def family_join_commit(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    code = message.text.strip()
    if not code:
        await message.answer("Код не может быть пустым.")
        return

    try:
        result = await services.family.join_by_code(actor_id=user.id, code=code)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.clear()
    await message.answer(
        "Вы подключены к семейной таблице.\n"
        f"ID семьи: {result.family_id}\n"
        f"Роль: {_role_label(result.role.value)}",
    )
    await _send_family_panel(message, services, user.id)


@router.message(Command("join"))
async def join_command(message: Message, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return

    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: /join <код>")
        return

    code = parts[1].strip()
    if not code:
        await message.answer("Формат: /join <код>")
        return

    try:
        result = await services.family.join_by_code(actor_id=user.id, code=code)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await message.answer(
        "Вы подключены к семейной таблице.\n"
        f"ID семьи: {result.family_id}\n"
        f"Роль: {_role_label(result.role.value)}",
    )
