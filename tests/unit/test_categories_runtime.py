from app.bot.keyboards.add_flow import category_keyboard
from app.domain.entities import CategoryRule
from app.domain.services.category_service import CategoryService
from app.utils.category_dictionary import load_default_category_rules


def test_category_keyboard_uses_short_callback_payloads() -> None:
    categories = [f"Очень длинная категория {i}" for i in range(1, 40)]
    keyboard = category_keyboard(
        categories,
        page=0,
        select_prefix="add_category",
        page_prefix="add_cat_page",
    )
    assert keyboard.inline_keyboard
    callback_values = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert any(value.startswith("add_category:") for value in callback_values)
    assert any(value.startswith("add_cat_page:") for value in callback_values)
    assert all(len(value) <= 64 for value in callback_values)


def test_merge_default_and_sheet_categories_prefers_sheet_override() -> None:
    defaults = load_default_category_rules()
    assert defaults
    first_default = defaults[0]
    sheet_categories = [
        CategoryRule(
            category=first_default.category,
            keywords=["manual-override"],
            enabled=False,
        ),
        CategoryRule(category="Custom Sheet", keywords=["custom"], enabled=True),
    ]
    merged = CategoryService._merge_default_and_sheet(sheet_categories=sheet_categories)
    by_key = {item.category.casefold(): item for item in merged}

    assert "custom sheet" in by_key
    overridden = by_key[first_default.category.casefold()]
    assert overridden.enabled is False
    assert overridden.keywords == ["manual-override"]
