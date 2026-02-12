from app.infra.google.template_builder import (
    DASHBOARD_BATCH_VALUES,
    DASHBOARD_PERIOD_OPTIONS,
    DASHBOARD_VERSION,
    USER_EXPENSES_HEADERS,
)


def test_dashboard_template_version_bumped() -> None:
    assert DASHBOARD_VERSION == "4"


def test_dashboard_template_period_options_are_russian() -> None:
    assert DASHBOARD_PERIOD_OPTIONS == [
        "Последние 7 дней",
        "Последние 30 дней",
        "Текущий месяц",
        "Текущий год",
        "Произвольный период",
    ]


def test_user_expenses_headers_are_compact() -> None:
    assert USER_EXPENSES_HEADERS == [
        "Название товара",
        "Количество",
        "Цена за единицу",
        "Кто купил",
        "Дата покупки",
    ]


def test_dashboard_uses_raw_expenses_projection() -> None:
    joined = " ".join(str(item) for item in DASHBOARD_BATCH_VALUES)
    assert "raw_expenses!N2:N" in joined
    assert "Нет данных" in joined
