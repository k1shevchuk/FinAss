from app.domain.entities import CategoryRule

EXPENSES_HEADERS = [
    "expense_id",
    "created_at_utc",
    "local_datetime",
    "timezone",
    "actor_telegram_id",
    "actor_name",
    "owner_telegram_id",
    "family_id",
    "source",
    "receipt_hash",
    "item_name",
    "quantity",
    "unit_price",
    "total_price",
    "currency",
    "category",
    "merchant",
    "notes",
]

CATEGORIES_HEADERS = ["category", "keywords", "enabled"]
USERS_HEADERS = ["telegram_id", "role", "display_name", "google_share_email"]
SETTINGS_HEADERS = ["key", "value"]
AUDIT_HEADERS = ["at_utc", "actor_telegram_id", "action", "details"]

DASHBOARD_VALUES = [
    ["Expense Tracker Dashboard"],
    [""],
    ["Metric", "Value"],
    ["Total Spent", '=IFERROR(SUM(expenses!N2:N),0)'],
    ["Transactions", '=IFERROR(COUNTA(expenses!A2:A),0)'],
    ["Average Check", '=IFERROR(B4/B5,0)'],
    [""],
    ["Category", "Total"],
    [
        '=IFERROR(QUERY(expenses!A1:R,"select P, sum(N) where P is not null group by P order by sum(N) desc label P \'Category\', sum(N) \'Total\'",1),{"No data","0"})',
    ],
    [""],
    ["Month", "Total"],
    [
        '=IFERROR(QUERY({ARRAYFORMULA(IF(LEN(expenses!C2:C),TEXT(DATEVALUE(LEFT(expenses!C2:C,10)),"YYYY-MM"),)),expenses!N2:N},"select Col1, sum(Col2) where Col1 is not null group by Col1 order by Col1 label Col1 \'Month\', sum(Col2) \'Total\'",0),{"No data","0"})',
    ],
]


def default_categories() -> list[CategoryRule]:
    return [
        CategoryRule(category="Продукты", keywords=["молоко", "хлеб", "сыр", "food", "еда"]),
        CategoryRule(category="Транспорт", keywords=["такси", "metro", "bus", "бензин"]),
        CategoryRule(category="Дом", keywords=["коммунал", "ремонт", "ikea"]),
        CategoryRule(category="Здоровье", keywords=["аптека", "лекар", "doctor"]),
        CategoryRule(category="Кафе и рестораны", keywords=["restaurant", "coffee", "кафе"]),
        CategoryRule(category="Подписки", keywords=["subscription", "netflix", "spotify"]),
        CategoryRule(category="Одежда", keywords=["shirt", "shoes", "одежд"]),
        CategoryRule(category="Развлечения", keywords=["кино", "cinema", "game"]),
        CategoryRule(category="Другое", keywords=[], enabled=True),
    ]
