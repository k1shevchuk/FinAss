from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.menu import BTN_REPORT, onboarding_mode_keyboard
from app.bot.keyboards.report import report_period_keyboard
from app.bot.states.report import ReportStates
from app.domain.entities import ReportPeriod
from app.domain.services.container import AppServices
from app.domain.value_objects import ReportPeriodKind

router = Router()


@router.message(Command("report"))
@router.message(F.text == BTN_REPORT)
async def report_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Выберите период отчета:", reply_markup=report_period_keyboard())


@router.callback_query(F.data.startswith("report:"))
async def report_generate(
    callback: CallbackQuery,
    state: FSMContext,
    services: AppServices,
) -> None:
    if not callback.from_user or not isinstance(callback.message, Message) or callback.data is None:
        return

    actor_family = await services.family.get_actor_family(callback.from_user.id)
    if not actor_family:
        await callback.message.answer(
            "Сначала подключите Google Таблицу в онбординге.",
            reply_markup=onboarding_mode_keyboard(),
        )
        await callback.answer()
        return

    family_id, _, _, timezone, _ = actor_family
    period_key = callback.data.split(":", 1)[1]

    if period_key == "custom":
        await state.set_state(ReportStates.waiting_custom_range)
        await callback.message.answer(
            "Введите период в формате: YYYY-MM-DD YYYY-MM-DD\nПример: 2026-02-01 2026-02-29"
        )
        await callback.answer()
        return

    if period_key in {"week", "30d"}:
        now_utc = datetime.now(tz=UTC)
        days = 7 if period_key == "week" else 30
        period = ReportPeriod(
            kind=ReportPeriodKind.CUSTOM,
            from_utc=now_utc - timedelta(days=days - 1),
            to_utc=now_utc,
        )
        period_label = "7 дней" if period_key == "week" else "30 дней"
    else:
        kind = ReportPeriodKind(period_key)
        period = await services.report.build_period(kind=kind, tz=timezone)
        period_label = {
            ReportPeriodKind.MONTH: "Месяц",
            ReportPeriodKind.YEAR: "Год",
        }.get(kind, kind.value)

    await state.clear()
    await _send_report(
        message=callback.message,
        services=services,
        family_id=family_id,
        period=period,
        timezone=timezone,
        period_label=period_label,
        actor_id=callback.from_user.id,
    )
    await callback.answer()


@router.message(ReportStates.waiting_custom_range, F.text)
async def report_custom_range(
    message: Message,
    state: FSMContext,
    services: AppServices,
) -> None:
    user = message.from_user
    if not user or not message.text:
        return

    actor_family = await services.family.get_actor_family(user.id)
    if not actor_family:
        await state.clear()
        await message.answer(
            "Сначала подключите Google Таблицу в онбординге.",
            reply_markup=onboarding_mode_keyboard(),
        )
        return

    family_id, _, _, timezone, _ = actor_family
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Неверный формат. Пример: 2026-02-01 2026-02-29")
        return

    try:
        start_local = datetime.fromisoformat(parts[0])
        end_local = datetime.fromisoformat(parts[1])
    except ValueError:
        await message.answer("Неверная дата. Используйте формат YYYY-MM-DD")
        return

    if end_local < start_local:
        await message.answer("Дата окончания должна быть позже даты начала.")
        return

    tzinfo = ZoneInfo(timezone)
    start_local = start_local.replace(tzinfo=tzinfo)
    end_local = end_local.replace(hour=23, minute=59, second=59, tzinfo=tzinfo)

    period = ReportPeriod(
        kind=ReportPeriodKind.CUSTOM,
        from_utc=start_local.astimezone(UTC),
        to_utc=end_local.astimezone(UTC),
    )
    await state.clear()
    await _send_report(
        message=message,
        services=services,
        family_id=family_id,
        period=period,
        timezone=timezone,
        period_label=f"{parts[0]} .. {parts[1]}",
        actor_id=user.id,
    )


async def _send_report(
    *,
    message: Message,
    services: AppServices,
    family_id,
    period: ReportPeriod,
    timezone: str,
    period_label: str,
    actor_id: int,
) -> None:
    report = await services.report.generate(family_id=family_id, period=period, tz=timezone)
    avg_check = Decimal("0")
    if report.totals.expenses_count > 0:
        avg_check = report.totals.total / Decimal(report.totals.expenses_count)
    top_category = report.by_category[0].category if report.by_category else "Нет данных"
    period_balance = report.net_change

    try:
        main_balance, savings_balance, currency = await services.accounts.get_balances(
            actor_id=actor_id
        )
    except Exception:  # noqa: BLE001
        main_balance, savings_balance = Decimal("0"), Decimal("0")
        currency = report.totals.currency

    lines = [
        f"Отчет: {period_label}",
        f"Итого расходов: {report.totals.total:.2f} {report.totals.currency}",
        f"Операций: {report.totals.expenses_count}",
        f"Средний чек: {avg_check:.2f} {report.totals.currency}",
        f"Топ категория: {top_category}",
        f"Чистое изменение баланса за период: {period_balance:.2f} {report.totals.currency}",
        "",
        "Операции по счетам за период:",
        f"- Пополнено основного: {report.topup_main:.2f} {report.totals.currency}",
        f"- Расходы с основного: {report.spent_main:.2f} {report.totals.currency}",
        f"- Переведено в накопления: {report.transferred_to_savings:.2f} {report.totals.currency}",
        f"- Списано из накоплений: {report.spent_from_savings:.2f} {report.totals.currency}",
        "",
        "Текущие балансы:",
        f"- Основной: {main_balance:.2f} {currency}",
        f"- Накопительный: {savings_balance:.2f} {currency}",
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

    lines.append("")
    lines.append("Топ магазинов:")
    merchants = [(name, total) for name, total in report.top_merchants if name != "N/A"]
    if merchants:
        lines.extend([f"- {name}: {total:.2f}" for name, total in merchants])
    elif report.top_merchants:
        lines.append("- Магазины не указаны в записях.")
    else:
        lines.append("- Нет данных")

    if report.by_category:
        lines.append("")
        lines.append("График категорий:")
        lines.extend(_text_bar_chart(report.by_category, report.totals.total))

    await message.answer("\n".join(lines))


def _text_bar_chart(by_category, total: Decimal) -> list[str]:
    chart: list[str] = []
    if total <= 0:
        return chart
    for item in by_category[:6]:
        share = float(item.total / total) if total else 0.0
        bar = "█" * max(1, int(round(share * 20)))
        chart.append(f"{item.category}: {bar} {share * 100:.1f}%")
    return chart
