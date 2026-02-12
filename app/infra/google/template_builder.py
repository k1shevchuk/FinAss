from app.domain.entities import CategoryRule
from app.utils.category_dictionary import load_default_category_rules

DASHBOARD_TAB = "Сводка"
EXPENSES_TAB = "Покупки"
RAW_EXPENSES_TAB = "raw_expenses"
CATEGORIES_TAB = "categories"
USERS_TAB = "users"
SETTINGS_TAB = "settings"
AUDIT_TAB = "audit"
LEDGER_TAB = "ledger"

# Hidden technical projection used by bot/services.
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

# User-facing "Покупки" sheet.
USER_EXPENSES_HEADERS = [
    "Название товара",
    "Категория",
    "Количество",
    "Цена за единицу",
    "Итого",
    "Кто купил",
    "Дата покупки",
]

CATEGORIES_HEADERS = ["category", "keywords", "enabled"]
USERS_HEADERS = ["telegram_id", "role", "display_name", "google_share_email"]
SETTINGS_HEADERS = ["key", "value"]
AUDIT_HEADERS = ["at_utc", "actor_telegram_id", "action", "details"]
LEDGER_HEADERS = [
    "entry_id",
    "at_utc",
    "local_datetime",
    "timezone",
    "actor_telegram_id",
    "owner_telegram_id",
    "type",
    "amount",
    "currency",
    "note",
]

# Bump to force safe dashboard refresh for existing sheets.
DASHBOARD_VERSION = "5"

DASHBOARD_PERIOD_OPTIONS = [
    "Последние 7 дней",
    "Последние 30 дней",
    "Текущий месяц",
    "Текущий год",
    "Произвольный период",
]

# EN formulas + comma separators. Gateway enforces spreadsheet locale=en_US for compatibility.
DASHBOARD_BATCH_VALUES = [
    {"range": f"{DASHBOARD_TAB}!A1:H1", "values": [["Сводка расходов семьи", "", "", "", "", "", "", ""]]},
    {
        "range": f"{DASHBOARD_TAB}!A3:D5",
        "values": [
            ["Об этом листе", "", "", ""],
            [
                "Здесь автоматически считается сводка по покупкам и счетам.",
                "",
                "",
                "",
            ],
            ["Заполняйте траты только через бота (лист «expenses» не редактируйте вручную).", "", "", ""],
        ],
    },
    {
        "range": f"{DASHBOARD_TAB}!F3:H5",
        "values": [
            ["Важно", "", ""],
            ["Формулы обновляются автоматически.", "", ""],
            ["Если таблица выглядит странно — нажмите /start для авто-обновления шаблона.", "", ""],
        ],
    },
    {
        "range": f"{DASHBOARD_TAB}!A7:B9",
        "values": [
            ["Период", "Последние 30 дней"],
            ["Дата с", ""],
            ["Дата по", ""],
        ],
    },
    {"range": f"{DASHBOARD_TAB}!H1:I1", "values": [["period_start", "period_end"]]},
    {
        "range": f"{DASHBOARD_TAB}!H2:I2",
        "values": [
            [
                '=IFERROR(SWITCH(B7,"Последние 7 дней",TODAY()-6,"Последние 30 дней",TODAY()-29,"Текущий месяц",EOMONTH(TODAY(),-1)+1,"Текущий год",DATE(YEAR(TODAY()),1,1),"Произвольный период",IF(B8="",TODAY()-29,B8),TODAY()-29),TODAY()-29)',
                '=IFERROR(SWITCH(B7,"Произвольный период",IF(B9="",TODAY(),B9),TODAY()),TODAY())',
            ]
        ],
    },
    {"range": f"{DASHBOARD_TAB}!A11:B11", "values": [["Показатель", "Значение"]]},
    {
        "range": f"{DASHBOARD_TAB}!A12:B15",
        "values": [
            [
                "Сумма расходов",
                '=IFERROR(SUM(FILTER(raw_expenses!N2:N,raw_expenses!N2:N<>"",IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)<=I2)),0)',
            ],
            [
                "Количество покупок",
                '=IFERROR(COUNTA(FILTER(raw_expenses!A2:A,raw_expenses!A2:A<>"",IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)<=I2)),0)',
            ],
            ["Средний чек", "=IFERROR(B12/B13,0)"],
            ["Топ категория", '=IFERROR(INDEX(J2:J220,MATCH(MAX(K2:K220),K2:K220,0)),"Нет данных")'],
        ],
    },
    {"range": f"{DASHBOARD_TAB}!J1:K1", "values": [["chart_category", "chart_total"]]},
    {
        "range": f"{DASHBOARD_TAB}!J2:K2",
        "values": [
            [
                '=IFERROR(QUERY(FILTER({raw_expenses!P2:P,raw_expenses!N2:N},raw_expenses!P2:P<>"",raw_expenses!N2:N<>"",IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)<=I2),"select Col1,sum(Col2) group by Col1 order by sum(Col2) desc label Col1 \'\',sum(Col2) \'\'",0),{"Нет данных",0})',
                "",
            ]
        ],
    },
    {"range": f"{DASHBOARD_TAB}!L1:M1", "values": [["chart_month", "chart_month_total"]]},
    {
        "range": f"{DASHBOARD_TAB}!L2:M2",
        "values": [
            [
                '=IFERROR(QUERY(FILTER({TEXT(IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0),"yyyy-mm"),raw_expenses!N2:N},raw_expenses!N2:N<>"",IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)<=I2),"select Col1,sum(Col2) group by Col1 order by Col1 label Col1 \'\',sum(Col2) \'\'",0),{"Нет данных",0})',
                "",
            ]
        ],
    },
    {"range": f"{DASHBOARD_TAB}!D11:E11", "values": [["Счета", "Значение"]]},
    {
        "range": f"{DASHBOARD_TAB}!D12:E16",
        "values": [
            [
                "Основной счёт",
                '=IFERROR(VALUE(INDEX(FILTER(settings!B2:B,settings!A2:A="main_balance"),1)),0)',
            ],
            [
                "Накопительный счёт",
                '=IFERROR(VALUE(INDEX(FILTER(settings!B2:B,settings!A2:A="savings_balance"),1)),0)',
            ],
            [
                "Валюта",
                '=IFERROR(INDEX(FILTER(settings!B2:B,settings!A2:A="currency"),1),"RUB")',
            ],
            [
                "В накопления за период",
                '=IFERROR(SUM(FILTER(ledger!H2:H,ledger!G2:G="transfer_to_savings",IFERROR(DATEVALUE(LEFT(ledger!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(ledger!C2:C,10)),0)<=I2)),0)',
            ],
            [
                "Списано из накоплений",
                '=IFERROR(SUM(FILTER(ledger!H2:H,ledger!G2:G="spend_from_savings",IFERROR(DATEVALUE(LEFT(ledger!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(ledger!C2:C,10)),0)<=I2)),0)',
            ],
        ],
    },
    {"range": f"{DASHBOARD_TAB}!A18:B18", "values": [["Категория", "Сумма"]]},
    {
        "range": f"{DASHBOARD_TAB}!A19:B19",
        "values": [
            [
                '=IFERROR(QUERY(FILTER({raw_expenses!P2:P,raw_expenses!N2:N},raw_expenses!P2:P<>"",raw_expenses!N2:N<>"",IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)<=I2),"select Col1,sum(Col2) group by Col1 order by sum(Col2) desc label Col1 \'\',sum(Col2) \'\'",0),{"Нет данных",0})',
                "",
            ]
        ],
    },
    {"range": f"{DASHBOARD_TAB}!D18:E18", "values": [["Месяц", "Сумма расходов"]]},
    {
        "range": f"{DASHBOARD_TAB}!D19:E19",
        "values": [
            [
                '=IFERROR(QUERY(FILTER({TEXT(IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0),"yyyy-mm"),raw_expenses!N2:N},raw_expenses!N2:N<>"",IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)<=I2),"select Col1,sum(Col2) group by Col1 order by Col1 label Col1 \'\',sum(Col2) \'\'",0),{"Нет данных",0})',
                "",
            ]
        ],
    },
    {"range": f"{DASHBOARD_TAB}!A35:B35", "values": [["Топ товаров", "Сумма"]]},
    {
        "range": f"{DASHBOARD_TAB}!A36:B36",
        "values": [
            [
                '=IFERROR(QUERY(FILTER({raw_expenses!K2:K,raw_expenses!N2:N},raw_expenses!K2:K<>"",raw_expenses!N2:N<>"",IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)<=I2),"select Col1,sum(Col2) group by Col1 order by sum(Col2) desc label Col1 \'\',sum(Col2) \'\'",0),{"Нет данных",0})',
                "",
            ]
        ],
    },
    {"range": f"{DASHBOARD_TAB}!D35:E35", "values": [["Кто покупал", "Сумма"]]},
    {
        "range": f"{DASHBOARD_TAB}!D36:E36",
        "values": [
            [
                '=IFERROR(QUERY(FILTER({raw_expenses!F2:F,raw_expenses!N2:N},raw_expenses!F2:F<>"",raw_expenses!N2:N<>"",IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)>=H2,IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0)<=I2),"select Col1,sum(Col2) group by Col1 order by sum(Col2) desc label Col1 \'\',sum(Col2) \'\'",0),{"Нет данных",0})',
                "",
            ]
        ],
    },
    {
        "range": f"{DASHBOARD_TAB}!A52:F52",
        "values": [
            [
                "Помесячная сводка",
                "Пополнения",
                "Расходы",
                "Баланс периода",
                "В накопления",
                "Из накоплений",
            ]
        ],
    },
    {
        "range": f"{DASHBOARD_TAB}!A53:F53",
        "values": [
            [
                '=IFERROR(QUERY({TEXT(IFERROR(DATEVALUE(LEFT(raw_expenses!C2:C,10)),0),"yyyy-mm"),0,VALUE(raw_expenses!N2:N),0,0,0;TEXT(IFERROR(DATEVALUE(LEFT(ledger!C2:C,10)),0),"yyyy-mm"),IF(ledger!G2:G="topup_main",VALUE(ledger!H2:H),0),0,IF(ledger!G2:G="transfer_to_savings",VALUE(ledger!H2:H),0),IF(ledger!G2:G="spend_from_savings",VALUE(ledger!H2:H),0),0},"select Col1,sum(Col2),sum(Col3),sum(Col2)-sum(Col3),sum(Col4),sum(Col5) where Col1 is not null group by Col1 order by Col1 label Col1 \'\',sum(Col2) \'\',sum(Col3) \'\',sum(Col2)-sum(Col3) \'\',sum(Col4) \'\',sum(Col5) \'\'",0),{"Нет данных",0,0,0,0,0})',
                "",
                "",
                "",
                "",
                "",
            ]
        ],
    },
]


def default_categories() -> list[CategoryRule]:
    return load_default_category_rules()
