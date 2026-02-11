from app.domain.entities import CategoryRule
from app.utils.category_dictionary import load_default_category_rules

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
DASHBOARD_VERSION = "3"
DASHBOARD_PERIOD_OPTIONS = [
    "Last 7 days",
    "Last 30 days",
    "This month",
    "This year",
    "Custom range",
]

# EN/US Google Sheets formulas with comma separators for deterministic API writes.
DASHBOARD_BATCH_VALUES = [
    {"range": "dashboard!A1:D1", "values": [["Expense Tracker Dashboard", "", "", ""]]},
    {
        "range": "dashboard!A2:B4",
        "values": [["Period", "Last 30 days"], ["Custom From", ""], ["Custom To", ""]],
    },
    {
        "range": "dashboard!A6:B13",
        "values": [
            ["KPI", "Value"],
            [
                "Total Spent",
                '=IFERROR(SUM(FILTER(expenses!N2:N,expenses!N2:N<>"",INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10))))>=G2,INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10))))<=H2)),0)',
            ],
            [
                "Transactions",
                '=IFERROR(COUNTA(FILTER(expenses!A2:A,expenses!A2:A<>"",INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10))))>=G2,INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10))))<=H2)),0)',
            ],
            ["Average Check", "=IFERROR(B8/B9,0)"],
            ["Top Category", '=IFERROR(INDEX(A16:A,MATCH(MAX(B16:B),B16:B,0)),"N/A")'],
            [
                "Main Balance",
                '=IFERROR(VALUE(INDEX(FILTER(settings!B2:B,settings!A2:A="main_balance"),1)),0)',
            ],
            [
                "Savings Balance",
                '=IFERROR(VALUE(INDEX(FILTER(settings!B2:B,settings!A2:A="savings_balance"),1)),0)',
            ],
            ["Currency", '=IFERROR(INDEX(FILTER(settings!B2:B,settings!A2:A="currency"),1),"RUB")'],
        ],
    },
    {"range": "dashboard!A15:B15", "values": [["Category", "Total"]]},
    {
        "range": "dashboard!A16:B16",
        "values": [
            [
                '=IFERROR(QUERY(FILTER({expenses!P2:P,expenses!N2:N},expenses!P2:P<>"",expenses!N2:N<>"",INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10))))>=G2,INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10))))<=H2),"select Col1, sum(Col2) group by Col1 order by sum(Col2) desc label Col1 \'\', sum(Col2) \'\'",0),{"No data",0})',
                "",
            ]
        ],
    },
    {"range": "dashboard!D15:E15", "values": [["Month", "Total"]]},
    {
        "range": "dashboard!D16:E16",
        "values": [
            [
                '=IFERROR(QUERY(FILTER({TEXT(INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10)))),"yyyy-mm"),expenses!N2:N},expenses!N2:N<>"",INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10))))>=G2,INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10))))<=H2),"select Col1, sum(Col2) group by Col1 order by Col1 label Col1 \'\', sum(Col2) \'\'",0),{"No data",0})',
                "",
            ]
        ],
    },
    {"range": "dashboard!A33:F33", "values": [["Monthly Budget Summary", "", "", "", "", ""]]},
    {
        "range": "dashboard!A35:F35",
        "values": [
            [
                "Month",
                "Topups",
                "Expenses",
                "Net Flow",
                "To Savings",
                "From Savings",
            ]
        ],
    },
    {
        "range": "dashboard!A36:F36",
        "values": [
            [
                '=IFERROR(QUERY({TEXT(INT(IFERROR(VALUE(LEFT(expenses!C2:C,10)),DATEVALUE(LEFT(expenses!C2:C,10)))),"yyyy-mm"),0,VALUE(expenses!N2:N),0,0,0;TEXT(INT(IFERROR(VALUE(LEFT(ledger!C2:C,10)),DATEVALUE(LEFT(ledger!C2:C,10)))),"yyyy-mm"),IF(ledger!G2:G="topup_main",VALUE(ledger!H2:H),0),0,0,IF(ledger!G2:G="transfer_to_savings",VALUE(ledger!H2:H),0),IF(ledger!G2:G="spend_from_savings",VALUE(ledger!H2:H),0)},"select Col1, sum(Col2), sum(Col3), sum(Col2)-sum(Col3), sum(Col5), sum(Col6) where Col1 is not null group by Col1 order by Col1 label Col1 \'\', sum(Col2) \'\', sum(Col3) \'\', sum(Col2)-sum(Col3) \'\', sum(Col5) \'\', sum(Col6) \'\'",0),{"No data",0,0,0,0,0})',
                "",
                "",
                "",
                "",
                "",
            ]
        ],
    },
    {
        "range": "dashboard!G1:H2",
        "values": [
            ["period_start", "period_end"],
            [
                '=IFERROR(SWITCH(B2,"Last 7 days",TODAY()-6,"Last 30 days",TODAY()-29,"This month",EOMONTH(TODAY(),-1)+1,"This year",DATE(YEAR(TODAY()),1,1),"Custom range",IF(B3="",TODAY()-29,B3),TODAY()-29),TODAY()-29)',
                '=IFERROR(SWITCH(B2,"Custom range",IF(B4="",TODAY(),B4),TODAY()),TODAY())',
            ],
        ],
    },
]


def default_categories() -> list[CategoryRule]:
    return load_default_category_rules()
