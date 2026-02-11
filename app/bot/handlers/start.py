from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from structlog.stdlib import get_logger

from app.bot.states.onboarding import OnboardingStates
from app.domain.services.container import AppServices
from app.utils.masking import mask_email
from app.utils.validation import extract_google_sheet_id, is_valid_email

router = Router()
logger = get_logger(__name__)


@router.message(CommandStart())
async def start_command(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user:
        return
    actor_family = await services.family.get_actor_family(user.id)
    if actor_family:
        await message.answer(
            "You are already connected. Commands:\n"
            "/add /scan /report /categories /family /settings /help"
        )
        return

    await state.set_state(OnboardingStates.waiting_google_email)
    await message.answer(
        "Expense Tracker onboarding:\n"
        "1) Send Google email -> bot creates a new spreadsheet and shares it.\n"
        "2) Send existing Google Spreadsheet link/ID -> bot connects your own sheet.\n\n"
        "Security: do not use public \"anyone can edit\" links."
    )


@router.message(OnboardingStates.waiting_google_email, F.text)
async def onboarding_input(message: Message, state: FSMContext, services: AppServices) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    raw = message.text.strip()
    display_name = user.full_name or str(user.id)

    try:
        if is_valid_email(raw):
            sheet_id, sheet_url = await services.onboarding.ensure_user_and_family(
                telegram_id=user.id,
                username=user.username,
                display_name=display_name,
                language_code=user.language_code,
                google_share_email=raw,
            )
            logger.info(
                "onboarding.completed.auto_create",
                telegram_id=user.id,
                sheet_id=sheet_id,
                email_masked=mask_email(raw),
            )
            await state.clear()
            await message.answer(
                "Done! Spreadsheet created and shared.\n"
                f"Open: {sheet_url}\n\n"
                "Next: /add, /scan, /report"
            )
            return

        sheet_link_id = extract_google_sheet_id(raw)
        if sheet_link_id:
            linked_sheet_id, linked_sheet_url = await services.onboarding.attach_existing_spreadsheet(
                telegram_id=user.id,
                username=user.username,
                display_name=display_name,
                language_code=user.language_code,
                sheet_id=sheet_link_id,
            )
            logger.info(
                "onboarding.completed.attach_existing",
                telegram_id=user.id,
                sheet_id=linked_sheet_id,
            )
            await state.clear()
            await message.answer(
                "Done! Your existing spreadsheet is connected.\n"
                f"Open: {linked_sheet_url}\n\n"
                "Next: /add, /scan, /report"
            )
            return

        await message.answer(
            "Input is invalid.\n"
            "Send Google email (name@gmail.com) OR Google Spreadsheet link/ID."
        )
        return
    except PermissionError as exc:
        logger.warning(
            "onboarding.permission_error",
            telegram_id=user.id,
            error=str(exc),
        )
        await message.answer(
            "Cannot complete onboarding.\n"
            f"{exc}\n\n"
            "Check Google setup and run /start again."
        )
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "onboarding.unexpected_error",
            telegram_id=user.id,
            error=str(exc),
        )
        await message.answer(
            "Onboarding failed due to Google API error.\n"
            "Check credentials/APIs and run /start again."
        )
        return
