from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.report import report_period_keyboard
from app.domain.services.container import AppServices
from app.domain.value_objects import ReportPeriodKind

router = Router()


@router.message(Command("report"))
async def report_start(message: Message) -> None:
    await message.answer("Выберите период отчета:", reply_markup=report_period_keyboard())


@router.callback_query(F.data.startswith("report:"))
async def report_generate(callback: CallbackQuery, services: AppServices) -> None:
    if not callback.from_user or not callback.message or callback.data is None:
        return
    actor_family = await services.family.get_actor_family(callback.from_user.id)
    if not actor_family:
        await callback.message.answer("Сначала выполните /start и подключите таблицу.")
        await callback.answer()
        return
    family_id, _, _, timezone, _ = actor_family
    period_key = callback.data.split(":", 1)[1]
    kind = ReportPeriodKind(period_key)
    period = await services.report.build_period(kind=kind, tz=timezone)
    report = await services.report.generate(family_id=family_id, period=period, tz=timezone)

    lines = [
        f"Отчет: {kind.value}",
        f"Итого: {report.totals.total:.2f} {report.totals.currency}",
        f"Операций: {report.totals.expenses_count}",
        "",
        "По категориям:",
    ]
    if report.by_category:
        lines.extend([f"- {item.category}: {item.total:.2f}" for item in report.by_category[:10]])
    else:
        lines.append("- Нет данных за выбранный период")
    lines.append("")
    lines.append("Топ товаров:")
    if report.top_items:
        lines.extend([f"- {name}: {total:.2f}" for name, total in report.top_items])
    else:
        lines.append("- Нет данных")

    await callback.message.answer("\n".join(lines))
    await callback.answer()
