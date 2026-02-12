from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.keyboards.menu import BTN_CATEGORIES, main_menu_keyboard, onboarding_mode_keyboard
from app.bot.states.categories import CategoryStates
from app.domain.services.container import AppServices

router = Router()


def categories_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить", callback_data="cat:add")
    builder.button(text="✅ Включить", callback_data="cat:enable")
    builder.button(text="⛔ Выключить", callback_data="cat:disable")
    builder.button(text="🧩 Синхр. из JSON", callback_data="cat:sync_defaults")
    builder.button(text="🔄 Обновить", callback_data="cat:refresh")
    builder.button(text="🏠 Меню", callback_data="cat:menu")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


async def _send_categories_panel(message: Message, services: AppServices, actor_id: int) -> None:
    categories = await services.categories.list_categories(actor_id)
    if not categories:
        await message.answer(
            "Категории не найдены. Сначала подключите таблицу.",
            reply_markup=onboarding_mode_keyboard(),
        )
        return

    lines = [f"Категории ({len(categories)}):"]
    preview_limit = 25
    for category in categories[:preview_limit]:
        status = "вкл" if category.enabled else "выкл"
        preview_keywords = category.keywords[:5]
        suffix = " …" if len(category.keywords) > 5 else ""
        keywords = (", ".join(preview_keywords) + suffix) if preview_keywords else "-"
        lines.append(f"• {category.category} [{status}] — {keywords}")
    if len(categories) > preview_limit:
        lines.append(f"… и еще {len(categories) - preview_limit} категорий")
    lines.append("")
    lines.append("Доступные действия: добавить, включить/выключить, синхронизировать из JSON.")

    await message.answer("\n".join(lines), reply_markup=categories_actions_keyboard())


@router.message(Command("categories"))
@router.message(F.text == BTN_CATEGORIES)
async def categories_start(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    await state.clear()
    await _send_categories_panel(message, services, user.id)


@router.callback_query(F.data == "cat:refresh")
async def categories_refresh(
    callback: CallbackQuery,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = callback.from_user
    if not isinstance(callback.message, Message) or not user:
        return
    await state.clear()
    await _send_categories_panel(callback.message, services, user.id)
    await callback.answer()


@router.callback_query(F.data == "cat:sync_defaults")
async def categories_sync_defaults(
    callback: CallbackQuery,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = callback.from_user
    if not isinstance(callback.message, Message) or not user:
        return
    await state.clear()
    added = await services.categories.sync_defaults_to_sheet(user.id)
    services.category_matcher.invalidate(actor_id=user.id)
    await callback.message.answer(f"Синхронизация завершена. Добавлено категорий: {added}.")
    await _send_categories_panel(callback.message, services, user.id)
    await callback.answer()


@router.callback_query(F.data == "cat:add")
async def categories_add_request(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await callback.message.answer(
            "Введите новую категорию в формате:\n"
            "Название | ключ1,ключ2\n"
            "Пример: Продукты | молоко,хлеб,сыр"
        )
    await state.set_state(CategoryStates.waiting_add_payload)
    await callback.answer()


@router.callback_query(F.data == "cat:enable")
async def categories_enable_request(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await callback.message.answer("Введите название категории, которую нужно включить.")
    await state.set_state(CategoryStates.waiting_enable_name)
    await callback.answer()


@router.callback_query(F.data == "cat:disable")
async def categories_disable_request(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await callback.message.answer("Введите название категории, которую нужно выключить.")
    await state.set_state(CategoryStates.waiting_disable_name)
    await callback.answer()


@router.callback_query(F.data == "cat:menu")
async def categories_back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Главное меню:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.message(CategoryStates.waiting_add_payload, F.text)
async def categories_add_commit(
    message: Message,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    payload = message.text.strip()
    if "|" not in payload:
        await message.answer("Формат неверный. Пример: Продукты | молоко,хлеб")
        return

    category_name, keywords_raw = [item.strip() for item in payload.split("|", maxsplit=1)]
    keywords = [keyword.strip() for keyword in keywords_raw.split(",") if keyword.strip()]
    if not category_name:
        await message.answer("Название категории не может быть пустым.")
        return

    await services.categories.add_category(user.id, category_name, keywords)
    services.category_matcher.invalidate(actor_id=user.id)
    await state.clear()
    await message.answer("Категория добавлена.")
    await _send_categories_panel(message, services, user.id)


@router.message(CategoryStates.waiting_enable_name, F.text)
async def categories_enable_commit(
    message: Message,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    updated = await services.categories.set_category_enabled(
        user.id,
        message.text.strip(),
        enabled=True,
    )
    services.category_matcher.invalidate(actor_id=user.id)
    await state.clear()
    if not updated:
        await message.answer("Категория не найдена.")
    else:
        await message.answer("Категория включена.")
    await _send_categories_panel(message, services, user.id)


@router.message(CategoryStates.waiting_disable_name, F.text)
async def categories_disable_commit(
    message: Message,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    updated = await services.categories.set_category_enabled(
        user.id,
        message.text.strip(),
        enabled=False,
    )
    services.category_matcher.invalidate(actor_id=user.id)
    await state.clear()
    if not updated:
        await message.answer("Категория не найдена.")
    else:
        await message.answer("Категория выключена.")
    await _send_categories_panel(message, services, user.id)
