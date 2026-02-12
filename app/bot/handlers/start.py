from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from structlog.stdlib import get_logger

from app.bot.keyboards.menu import (
    BTN_HELP,
    BTN_MENU,
    BTN_ONB_ATTACH,
    BTN_ONB_JOIN,
    main_menu_keyboard,
    onboarding_mode_keyboard,
)
from app.bot.states.onboarding import OnboardingStates
from app.domain.services.container import AppServices
from app.utils.validation import extract_google_sheet_id, parse_decimal

router = Router()
logger = get_logger(__name__)
SERVICE_ACCOUNT_EDITOR = "hydra-950@finassbobot.iam.gserviceaccount.com"


def _role_label(role: str) -> str:
    if role == "owner":
        return "владелец"
    if role == "editor":
        return "участник"
    return role


@router.message(CommandStart())
@router.message(F.text == BTN_MENU)
async def start_or_menu(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return

    actor_family = await services.family.get_actor_family(user.id)
    if actor_family:
        try:
            await services.onboarding.upgrade_existing_sheet_if_needed(
                telegram_id=user.id,
                display_name=user.full_name or str(user.id),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("onboarding.upgrade_existing_sheet.failed", error=str(exc))
        await state.clear()
        await message.answer(
            "Главное меню. Выберите действие кнопками ниже.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(OnboardingStates.waiting_setup_mode)
    await message.answer(
        "Привет! Я помогу вести личные и семейные расходы в Google Sheets.\n\n"
        "Перед подключением выдайте вашей таблице доступ «Редактор» для:\n"
        f"{SERVICE_ACCOUNT_EDITOR}\n\n"
        "Выберите действие:",
        reply_markup=onboarding_mode_keyboard(),
    )


@router.message(OnboardingStates.waiting_setup_mode, F.text == BTN_ONB_ATTACH)
async def onboarding_choose_attach(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.waiting_sheet_link)
    await message.answer(
        "Отправьте ссылку на Google Таблицу или только ее ID.\n"
        "Важно: у сервисного аккаунта должен быть доступ «Редактор» к этой таблице:\n"
        f"{SERVICE_ACCOUNT_EDITOR}"
    )


@router.message(OnboardingStates.waiting_setup_mode, F.text == BTN_ONB_JOIN)
async def onboarding_choose_join(message: Message, state: FSMContext) -> None:
    await state.set_state(OnboardingStates.waiting_join_code)
    await message.answer("Введите код приглашения для подключения к общей таблице.")


@router.message(OnboardingStates.waiting_setup_mode, F.text == BTN_HELP)
async def onboarding_choose_help(message: Message) -> None:
    await message.answer(
        "Нажмите «Подключить таблицу», если у вас уже есть своя таблица.\n"
        "Нажмите «Подключиться по коду», если вас пригласили в семейную таблицу."
    )


@router.message(OnboardingStates.waiting_setup_mode)
async def onboarding_choose_mode_invalid(message: Message) -> None:
    await message.answer(
        "Нажмите одну из кнопок: «Подключить таблицу» или «Подключиться по коду».",
        reply_markup=onboarding_mode_keyboard(),
    )


@router.message(
    StateFilter(None),
    F.text.in_([BTN_ONB_ATTACH, BTN_ONB_JOIN, BTN_HELP]),
)
async def onboarding_choose_mode_no_state(
    message: Message,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = message.from_user
    if not user or not message.text:
        return
    actor_family = await services.family.get_actor_family(user.id)
    if actor_family:
        await message.answer(
            "Вы уже подключены. Используйте главное меню.",
            reply_markup=main_menu_keyboard(),
        )
        return

    await state.set_state(OnboardingStates.waiting_setup_mode)
    if message.text == BTN_ONB_ATTACH:
        await onboarding_choose_attach(message, state)
        return
    if message.text == BTN_ONB_JOIN:
        await onboarding_choose_join(message, state)
        return
    await onboarding_choose_help(message)


@router.message(OnboardingStates.waiting_join_code, F.text)
async def onboarding_join_by_code(
    message: Message, state: FSMContext, services: AppServices
) -> None:
    user = message.from_user
    if not user or not message.text:
        return
    code = message.text.strip()
    if not code:
        await message.answer("Код не может быть пустым.")
        return

    try:
        result = await services.family.join_by_code(
            actor_id=user.id,
            code=code,
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return

    logger.info(
        "onboarding.join_by_code.completed",
        telegram_id=user.id,
        family_id=str(result.family_id),
        role=result.role.value,
    )
    await state.clear()
    await message.answer(
        "Вы подключены к общей таблице.\n"
        f"Роль: {_role_label(result.role.value)}\n"
        "Теперь можно работать через главное меню.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(OnboardingStates.waiting_sheet_link, F.text)
async def onboarding_attach_sheet(
    message: Message, state: FSMContext, services: AppServices
) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    sheet_id = extract_google_sheet_id(message.text.strip())
    if not sheet_id:
        await message.answer(
            "Не вижу корректный идентификатор Google Таблицы.\n"
            "Пришлите ссылку вида https://docs.google.com/spreadsheets/d/<ID>/edit"
        )
        return

    display_name = user.full_name or str(user.id)
    try:
        linked_sheet_id, linked_sheet_url = await services.onboarding.attach_existing_spreadsheet(
            telegram_id=user.id,
            username=user.username,
            display_name=display_name,
            language_code=user.language_code,
            sheet_id=sheet_id,
        )
        logger.info(
            "onboarding.completed.attach_existing",
            telegram_id=user.id,
            sheet_id=linked_sheet_id,
        )
        await state.update_data(
            onboarding_sheet_id=linked_sheet_id,
            onboarding_sheet_url=linked_sheet_url,
        )
        await state.set_state(OnboardingStates.waiting_initial_main_balance)
        await message.answer(
            "Готово! Таблица подключена.\n"
            f"Открыть: {linked_sheet_url}\n\n"
            "Введите начальный баланс основного счёта:",
        )
    except PermissionError as exc:
        logger.warning("onboarding.attach.permission_error", telegram_id=user.id, error=str(exc))
        await message.answer(
            "Не удалось подключить таблицу.\n"
            f"Причина: {exc}\n\n"
            "Убедитесь, что сервисному аккаунту выдан доступ «Редактор» к таблице:\n"
            f"{SERVICE_ACCOUNT_EDITOR}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("onboarding.attach.unexpected_error", telegram_id=user.id, error=str(exc))
        await message.answer(
            "Ошибка Google API при подключении таблицы.\nПроверьте доступы и попробуйте снова."
        )


@router.message(OnboardingStates.waiting_initial_main_balance, F.text)
async def onboarding_main_balance(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    try:
        main_balance = parse_decimal(message.text.strip())
    except ValueError:
        await message.answer("Некорректная сумма. Пример: 1000 или 1000.50")
        return
    await state.update_data(initial_main_balance=str(main_balance))
    await state.set_state(OnboardingStates.waiting_initial_savings_balance)
    await message.answer("Введите начальный баланс накопительного счёта:")


@router.message(OnboardingStates.waiting_initial_savings_balance, F.text)
async def onboarding_savings_balance(
    message: Message, state: FSMContext, services: AppServices
) -> None:
    user = message.from_user
    if not user or not message.text:
        return
    try:
        savings_balance = parse_decimal(message.text.strip())
    except ValueError:
        await message.answer("Некорректная сумма. Пример: 500 или 500.00")
        return

    data = await state.get_data()
    try:
        main_balance = parse_decimal(str(data.get("initial_main_balance", "0")))
    except ValueError:
        main_balance = parse_decimal("0")

    try:
        await services.accounts.initialize_balances(
            actor_id=user.id,
            actor_name=user.full_name or str(user.id),
            main_balance=main_balance,
            savings_balance=savings_balance,
        )
    except PermissionError:
        await message.answer("Только owner может задавать начальные балансы.")
        return
    except ValueError as exc:
        await message.answer(str(exc))
        return
    sheet_url = str(data.get("onboarding_sheet_url", ""))
    await state.clear()
    await message.answer(
        "Настройка завершена.\n"
        f"Таблица: {sheet_url}\n"
        "Теперь можно добавлять расходы кнопками ниже.",
        reply_markup=main_menu_keyboard(),
    )
