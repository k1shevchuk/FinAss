import asyncio
from collections import defaultdict
from typing import Any, Literal

from googleapiclient.errors import HttpError
from structlog.stdlib import get_logger

from app.config.settings import Settings
from app.domain.entities import (
    AppendResult,
    AuditRow,
    CategoryRule,
    ExpenseRow,
    OwnerContext,
    SpreadsheetInfo,
)
from app.infra.google.drive_sharing import DriveSharing
from app.infra.google.template_builder import (
    AUDIT_HEADERS,
    AUDIT_TAB,
    CATEGORIES_HEADERS,
    CATEGORIES_TAB,
    DASHBOARD_BATCH_VALUES,
    DASHBOARD_PERIOD_OPTIONS,
    DASHBOARD_TAB,
    DASHBOARD_VERSION,
    EXPENSES_HEADERS,
    EXPENSES_TAB,
    LEDGER_HEADERS,
    LEDGER_TAB,
    RAW_EXPENSES_TAB,
    SETTINGS_HEADERS,
    SETTINGS_TAB,
    USER_EXPENSES_HEADERS,
    USERS_HEADERS,
    USERS_TAB,
    default_categories,
)
from app.utils.retry import retry_async

logger = get_logger(__name__)


class GoogleSheetsGateway:
    def __init__(
        self,
        *,
        sheets_service: Any,
        drive_service: Any | None = None,
        drive_sharing: DriveSharing,
        settings: Settings,
    ) -> None:
        self._sheets: Any = sheets_service
        self._drive_service: Any | None = drive_service
        self._drive = drive_sharing
        self._settings = settings
        self._service_account_email: str | None = None

    async def create_spreadsheet(self, owner: OwnerContext) -> SpreadsheetInfo:
        _ = owner
        raise RuntimeError(
            "Spreadsheet creation flow is disabled. Use attach_existing_spreadsheet."
        )

    async def attach_existing_spreadsheet(
        self,
        *,
        sheet_id: str,
        owner: OwnerContext,
    ) -> SpreadsheetInfo:
        await self._ensure_template_tabs(
            sheet_id=sheet_id,
            rename_first_to_dashboard=False,
        )
        await self._write_template(sheet_id=sheet_id, owner=owner)
        return SpreadsheetInfo(
            sheet_id=sheet_id,
            sheet_url=f"https://docs.google.com/spreadsheets/d/{sheet_id}",
        )

    async def share_spreadsheet(
        self,
        *,
        sheet_id: str,
        email: str,
        role: Literal["writer", "reader"] = "writer",
    ) -> None:
        await self._drive.share_spreadsheet(sheet_id=sheet_id, email=email, role=role)

    async def append_expenses(self, *, sheet_id: str, rows: list[ExpenseRow]) -> AppendResult:
        if not rows:
            return AppendResult(updated_rows=0)
        values = [row.values for row in rows]
        body = {"values": values}

        async def _append() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .append(
                    spreadsheetId=sheet_id,
                    range=f"{RAW_EXPENSES_TAB}!A1",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
            )
            return await asyncio.to_thread(request.execute)

        result = await self._retry_http(_append)
        updated = result.get("updates", {}).get("updatedRows", len(rows))
        return AppendResult(updated_rows=int(updated))

    async def append_audit(self, *, sheet_id: str, rows: list[AuditRow]) -> AppendResult:
        if not rows:
            return AppendResult(updated_rows=0)
        body = {"values": [r.values for r in rows]}

        async def _append() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .append(
                    spreadsheetId=sheet_id,
                    range=f"{AUDIT_TAB}!A1",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
            )
            return await asyncio.to_thread(request.execute)

        result = await self._retry_http(_append)
        updated = result.get("updates", {}).get("updatedRows", len(rows))
        return AppendResult(updated_rows=int(updated))

    async def append_ledger(self, *, sheet_id: str, rows: list[list[str]]) -> AppendResult:
        if not rows:
            return AppendResult(updated_rows=0)
        body = {"values": rows}

        async def _append() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .append(
                    spreadsheetId=sheet_id,
                    range=f"{LEDGER_TAB}!A1",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
            )
            return await asyncio.to_thread(request.execute)

        try:
            result = await self._retry_http(_append)
        except HttpError as exc:
            if getattr(exc.resp, "status", None) != 400:
                raise
            await self._ensure_template_tabs(
                sheet_id=sheet_id,
                rename_first_to_dashboard=False,
            )
            result = await self._retry_http(_append)
        updated = result.get("updates", {}).get("updatedRows", len(rows))
        return AppendResult(updated_rows=int(updated))

    async def append_users(self, *, sheet_id: str, rows: list[list[str]]) -> AppendResult:
        if not rows:
            return AppendResult(updated_rows=0)
        body = {"values": rows}

        async def _append() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .append(
                    spreadsheetId=sheet_id,
                    range=f"{USERS_TAB}!A1",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
            )
            return await asyncio.to_thread(request.execute)

        result = await self._retry_http(_append)
        updated = result.get("updates", {}).get("updatedRows", len(rows))
        return AppendResult(updated_rows=int(updated))

    async def get_categories(self, *, sheet_id: str) -> list[CategoryRule]:
        async def _read() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range=f"{CATEGORIES_TAB}!A2:C")
            )
            return await asyncio.to_thread(request.execute)

        result = await self._retry_http(_read)
        parsed: list[CategoryRule] = []
        for row in result.get("values", []):
            category = str(row[0]).strip() if len(row) > 0 else ""
            keywords_raw = str(row[1]).strip() if len(row) > 1 else ""
            enabled_raw = str(row[2]).strip().lower() if len(row) > 2 else "true"
            if not category:
                continue
            parsed.append(
                CategoryRule(
                    category=category,
                    keywords=[p.strip() for p in keywords_raw.split(",") if p.strip()],
                    enabled=enabled_raw in {"true", "1", "yes"},
                )
            )
        return parsed

    async def get_settings(self, *, sheet_id: str) -> dict[str, str]:
        async def _read() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range=f"{SETTINGS_TAB}!A2:B")
            )
            return await asyncio.to_thread(request.execute)

        result = await self._retry_http(_read)
        out: dict[str, str] = {}
        for row in result.get("values", []):
            if len(row) < 2:
                continue
            out[str(row[0])] = str(row[1])
        return out

    async def set_setting(self, *, sheet_id: str, key: str, value: str) -> None:
        settings = await self.get_settings(sheet_id=sheet_id)
        if key in settings:
            rows = await self._read_range(sheet_id=sheet_id, range_name=f"{SETTINGS_TAB}!A2:B")
            row_index = 2
            for row in rows:
                if len(row) > 0 and str(row[0]) == key:
                    break
                row_index += 1
            await self._update_single_cell(
                sheet_id=sheet_id,
                range_name=f"{SETTINGS_TAB}!B{row_index}",
                value=value,
            )
            return
        await self._append_rows(sheet_id=sheet_id, range_name=f"{SETTINGS_TAB}!A1", rows=[[key, value]])

    async def add_category(self, *, sheet_id: str, category: str, keywords: list[str]) -> None:
        await self._append_rows(
            sheet_id=sheet_id,
            range_name=f"{CATEGORIES_TAB}!A1",
            rows=[[category, ", ".join(keywords), "true"]],
        )

    async def set_category_enabled(self, *, sheet_id: str, category: str, enabled: bool) -> bool:
        rows = await self._read_range(sheet_id=sheet_id, range_name=f"{CATEGORIES_TAB}!A2:C")
        row_index = 2
        for row in rows:
            if len(row) > 0 and str(row[0]).strip() == category:
                await self._update_single_cell(
                    sheet_id=sheet_id,
                    range_name=f"{CATEGORIES_TAB}!C{row_index}",
                    value="true" if enabled else "false",
                )
                return True
            row_index += 1
        return False

    async def read_expenses(self, *, sheet_id: str) -> list[dict[str, str]]:
        async def _read() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range=f"{RAW_EXPENSES_TAB}!A1:R")
            )
            return await asyncio.to_thread(request.execute)

        try:
            result = await self._retry_http(_read)
        except HttpError as exc:
            # Backward compatibility for old sheets where full data was stored in "expenses".
            if getattr(exc.resp, "status", None) != 400:
                raise

            async def _read_legacy() -> dict[str, Any]:
                request = (
                    self._sheets.spreadsheets()
                    .values()
                    .get(spreadsheetId=sheet_id, range=f"{EXPENSES_TAB}!A1:R")
                )
                return await asyncio.to_thread(request.execute)

            result = await self._retry_http(_read_legacy)
        values = result.get("values", [])
        if not values:
            return []
        headers = values[0]
        rows = values[1:]
        mapped: list[dict[str, str]] = []
        for row in rows:
            item = defaultdict(str)
            for index, key in enumerate(headers):
                if index < len(row):
                    item[str(key)] = str(row[index])
            mapped.append(dict(item))
        return mapped

    async def read_ledger(self, *, sheet_id: str) -> list[dict[str, str]]:
        async def _read() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .get(spreadsheetId=sheet_id, range=f"{LEDGER_TAB}!A1:J")
            )
            return await asyncio.to_thread(request.execute)

        try:
            result = await self._retry_http(_read)
        except HttpError as exc:
            if getattr(exc.resp, "status", None) == 400:
                return []
            raise
        values = result.get("values", [])
        if not values:
            return []
        headers = values[0]
        rows = values[1:]
        mapped: list[dict[str, str]] = []
        for row in rows:
            item = defaultdict(str)
            for index, key in enumerate(headers):
                if index < len(row):
                    item[str(key)] = str(row[index])
            mapped.append(dict(item))
        return mapped

    async def purge_actor_data(self, *, sheet_id: str, actor_telegram_id: int) -> None:
        actor = str(actor_telegram_id)

        expense_rows = await self._read_range(sheet_id=sheet_id, range_name=f"{RAW_EXPENSES_TAB}!A2:R")
        filtered_expenses = [
            row for row in expense_rows if len(row) <= 4 or str(row[4]).strip() != actor
        ]
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=RAW_EXPENSES_TAB,
            headers=EXPENSES_HEADERS,
            rows=filtered_expenses,
        )
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=EXPENSES_TAB,
            headers=USER_EXPENSES_HEADERS,
            rows=[],
        )
        await self._write_expenses_projection(sheet_id=sheet_id)

        users_rows = await self._read_range(sheet_id=sheet_id, range_name=f"{USERS_TAB}!A2:D")
        filtered_users = [
            row for row in users_rows if len(row) == 0 or str(row[0]).strip() != actor
        ]
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=USERS_TAB,
            headers=USERS_HEADERS,
            rows=filtered_users,
        )

        audit_rows = await self._read_range(sheet_id=sheet_id, range_name=f"{AUDIT_TAB}!A2:D")
        filtered_audit = [
            row for row in audit_rows if len(row) <= 1 or str(row[1]).strip() != actor
        ]
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=AUDIT_TAB,
            headers=AUDIT_HEADERS,
            rows=filtered_audit,
        )

        ledger_rows = await self._read_range(sheet_id=sheet_id, range_name=f"{LEDGER_TAB}!A2:J")
        filtered_ledger = [
            row for row in ledger_rows if len(row) <= 4 or str(row[4]).strip() != actor
        ]
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=LEDGER_TAB,
            headers=LEDGER_HEADERS,
            rows=filtered_ledger,
        )

    async def wipe_family_data(self, *, sheet_id: str) -> None:
        settings = await self.get_settings(sheet_id=sheet_id)
        currency = settings.get("currency", "RUB")
        timezone = settings.get("timezone", self._settings.default_timezone)
        rounding_mode = settings.get("rounding_mode", "HALF_UP")

        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=RAW_EXPENSES_TAB,
            headers=EXPENSES_HEADERS,
            rows=[],
        )
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=EXPENSES_TAB,
            headers=USER_EXPENSES_HEADERS,
            rows=[],
        )
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=USERS_TAB,
            headers=USERS_HEADERS,
            rows=[],
        )
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=AUDIT_TAB,
            headers=AUDIT_HEADERS,
            rows=[],
        )
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=LEDGER_TAB,
            headers=LEDGER_HEADERS,
            rows=[],
        )
        default_category_rows = [
            [item.category, ", ".join(item.keywords), "true" if item.enabled else "false"]
            for item in default_categories()
        ]
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=CATEGORIES_TAB,
            headers=CATEGORIES_HEADERS,
            rows=default_category_rows,
        )
        await self._replace_rows_with_header(
            sheet_id=sheet_id,
            tab_name=SETTINGS_TAB,
            headers=SETTINGS_HEADERS,
            rows=[
                ["currency", currency],
                ["timezone", timezone],
                ["rounding_mode", rounding_mode],
                ["main_balance", "0.00"],
                ["savings_balance", "0.00"],
                ["updated_at_utc", ""],
                ["dashboard_version", DASHBOARD_VERSION],
            ],
        )
        await self._write_expenses_projection(sheet_id=sheet_id)
        await self._write_dashboard(sheet_id=sheet_id)

    async def _write_template(self, *, sheet_id: str, owner: OwnerContext) -> None:
        headers_body = {
            "valueInputOption": "RAW",
            "data": [
                {"range": f"{DASHBOARD_TAB}!A1:H1", "values": [["Сводка расходов семьи", "", "", "", "", "", "", ""]]},
                {"range": f"{EXPENSES_TAB}!A1:E1", "values": [USER_EXPENSES_HEADERS]},
                {"range": f"{RAW_EXPENSES_TAB}!A1:R1", "values": [EXPENSES_HEADERS]},
                {"range": f"{CATEGORIES_TAB}!A1:C1", "values": [CATEGORIES_HEADERS]},
                {"range": f"{USERS_TAB}!A1:D1", "values": [USERS_HEADERS]},
                {"range": f"{SETTINGS_TAB}!A1:B1", "values": [SETTINGS_HEADERS]},
                {"range": f"{AUDIT_TAB}!A1:D1", "values": [AUDIT_HEADERS]},
                {"range": f"{LEDGER_TAB}!A1:J1", "values": [LEDGER_HEADERS]},
            ],
        }

        async def _batch_headers() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .batchUpdate(
                    spreadsheetId=sheet_id,
                    body=headers_body,
                )
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch_headers)
        await self._ensure_spreadsheet_properties(sheet_id=sheet_id, timezone=owner.timezone)
        await self._write_expenses_projection(sheet_id=sheet_id)
        await self._format_expenses_sheet(sheet_id=sheet_id)
        await self._write_dashboard(sheet_id=sheet_id)
        await self._ensure_default_categories(sheet_id=sheet_id)
        await self._ensure_owner_row(sheet_id=sheet_id, owner=owner)
        await self._ensure_default_settings(sheet_id=sheet_id, owner=owner)
        await self._apply_user_tab_visibility(sheet_id=sheet_id)

    async def _write_dashboard(self, *, sheet_id: str) -> None:
        async def _clear() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .clear(
                    spreadsheetId=sheet_id,
                    range=f"{DASHBOARD_TAB}!A1:Z500",
                    body={},
                )
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_clear)
        await self._batch_update_values(sheet_id=sheet_id, data=DASHBOARD_BATCH_VALUES)
        metadata = await self._get_spreadsheet_metadata(sheet_id=sheet_id)
        dashboard_sheet_id = metadata[DASHBOARD_TAB]
        await self._format_dashboard(sheet_id=sheet_id, dashboard_sheet_id=dashboard_sheet_id)
        await self._set_dashboard_period_validation(
            sheet_id=sheet_id,
            dashboard_sheet_id=dashboard_sheet_id,
        )
        await self._rebuild_dashboard_charts(
            sheet_id=sheet_id,
            dashboard_sheet_id=dashboard_sheet_id,
        )

    async def _write_expenses_projection(self, *, sheet_id: str) -> None:
        async def _clear() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .clear(
                    spreadsheetId=sheet_id,
                    range=f"{EXPENSES_TAB}!A2:E5000",
                    body={},
                )
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_clear)
        projection_formula = (
            '=IFERROR(ARRAYFORMULA(FILTER({raw_expenses!K2:K,raw_expenses!L2:L,raw_expenses!M2:M,raw_expenses!F2:F,IFERROR(TEXT(DATEVALUE(LEFT(raw_expenses!C2:C,10)),"dd.mm.yyyy"),LEFT(raw_expenses!C2:C,10))},raw_expenses!K2:K<>"")),{"Нет данных","","","",""})'
        )
        await self._update_single_cell(
            sheet_id=sheet_id,
            range_name=f"{EXPENSES_TAB}!A2",
            value=projection_formula,
        )

    async def _ensure_spreadsheet_properties(self, *, sheet_id: str, timezone: str) -> None:
        async def _batch() -> dict[str, Any]:
            request = self._sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={
                    "requests": [
                        {
                            "updateSpreadsheetProperties": {
                                "properties": {
                                    "locale": "en_US",
                                    "timeZone": timezone,
                                },
                                "fields": "locale,timeZone",
                            }
                        }
                    ]
                },
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch)

    async def _format_expenses_sheet(self, *, sheet_id: str) -> None:
        metadata = await self._get_spreadsheet_metadata(sheet_id=sheet_id)
        expenses_sheet_id = metadata.get(EXPENSES_TAB)
        if expenses_sheet_id is None:
            return
        requests: list[dict[str, Any]] = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": expenses_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 5,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColorStyle": {
                                "rgbColor": {"red": 0.9, "green": 0.94, "blue": 1.0}
                            },
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColorStyle)",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": expenses_sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": expenses_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 260},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": expenses_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": 4,
                    },
                    "properties": {"pixelSize": 160},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": expenses_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 4,
                        "endIndex": 5,
                    },
                    "properties": {"pixelSize": 170},
                    "fields": "pixelSize",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": expenses_sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 5000,
                        "startColumnIndex": 1,
                        "endColumnIndex": 3,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
        ]

        async def _batch() -> dict[str, Any]:
            request = self._sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": requests},
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch)

    async def _apply_user_tab_visibility(self, *, sheet_id: str) -> None:
        metadata = await self._get_spreadsheet_metadata(sheet_id=sheet_id)
        requests: list[dict[str, Any]] = []
        for title, tab_id in metadata.items():
            hidden = title not in {DASHBOARD_TAB, EXPENSES_TAB}
            requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": tab_id, "hidden": hidden},
                        "fields": "hidden",
                    }
                }
            )
        if not requests:
            return

        async def _batch() -> dict[str, Any]:
            request = self._sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": requests},
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch)

    async def _ensure_default_categories(self, *, sheet_id: str) -> None:
        rows = await self._read_range(sheet_id=sheet_id, range_name=f"{CATEGORIES_TAB}!A2:C")
        existing_categories = {
            str(row[0]).strip().casefold()
            for row in rows
            if len(row) > 0 and str(row[0]).strip()
        }
        rows_categories = [
            [item.category, ", ".join(item.keywords), "true" if item.enabled else "false"]
            for item in default_categories()
            if item.category.casefold() not in existing_categories
        ]
        if not rows_categories:
            return
        await self._append_rows(
            sheet_id=sheet_id,
            range_name=f"{CATEGORIES_TAB}!A1",
            rows=rows_categories,
        )

    async def _ensure_owner_row(self, *, sheet_id: str, owner: OwnerContext) -> None:
        rows = await self._read_range(sheet_id=sheet_id, range_name=f"{USERS_TAB}!A2:D")
        owner_id = str(owner.telegram_id)
        for row in rows:
            if len(row) > 0 and str(row[0]).strip() == owner_id:
                return
        await self._append_rows(
            sheet_id=sheet_id,
            range_name=f"{USERS_TAB}!A1",
            rows=[
                [
                    owner_id,
                    "owner",
                    owner.display_name,
                    owner.google_share_email,
                ]
            ],
        )

    async def _ensure_default_settings(self, *, sheet_id: str, owner: OwnerContext) -> None:
        settings = await self.get_settings(sheet_id=sheet_id)
        defaults = {
            "currency": owner.currency,
            "timezone": owner.timezone,
            "rounding_mode": "HALF_UP",
            "main_balance": "0.00",
            "savings_balance": "0.00",
            "updated_at_utc": "",
            "dashboard_version": DASHBOARD_VERSION,
        }
        for key, value in defaults.items():
            if key in settings:
                continue
            await self._append_rows(
                sheet_id=sheet_id,
                range_name=f"{SETTINGS_TAB}!A1",
                rows=[[key, value]],
            )

    async def _create_spreadsheet_in_service_account_drive(self, *, title: str) -> SpreadsheetInfo:
        body = {
            "properties": {"title": title},
            "sheets": [
                {"properties": {"title": DASHBOARD_TAB}},
                {"properties": {"title": EXPENSES_TAB}},
                {"properties": {"title": RAW_EXPENSES_TAB}},
                {"properties": {"title": CATEGORIES_TAB}},
                {"properties": {"title": USERS_TAB}},
                {"properties": {"title": SETTINGS_TAB}},
                {"properties": {"title": AUDIT_TAB}},
                {"properties": {"title": LEDGER_TAB}},
            ],
        }

        async def _create() -> dict[str, Any]:
            request = self._sheets.spreadsheets().create(
                body=body,
                fields="spreadsheetId,spreadsheetUrl",
            )
            return await asyncio.to_thread(request.execute)

        created = await self._retry_http(_create)
        sheet_id = str(created["spreadsheetId"])
        sheet_url = str(created["spreadsheetUrl"])
        return SpreadsheetInfo(sheet_id=sheet_id, sheet_url=sheet_url)

    async def _create_spreadsheet_in_folder(
        self,
        *,
        title: str,
        folder_id: str,
    ) -> SpreadsheetInfo:
        if self._drive_service is None:
            raise RuntimeError("Drive service is not initialized.")
        drive_service = self._drive_service

        async def _create() -> dict[str, Any]:
            request = drive_service.files().create(
                body={
                    "name": title,
                    "mimeType": "application/vnd.google-apps.spreadsheet",
                    "parents": [folder_id],
                },
                fields="id,webViewLink",
            )
            return await asyncio.to_thread(request.execute)

        created = await self._retry_http(_create)
        sheet_id = str(created["id"])
        sheet_url = str(
            created.get("webViewLink") or f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        )
        return SpreadsheetInfo(sheet_id=sheet_id, sheet_url=sheet_url)

    async def _assert_can_create_in_service_account_drive(self) -> None:
        if self._drive_service is None:
            return
        drive_service = self._drive_service

        async def _about() -> dict[str, Any]:
            request = drive_service.about().get(fields="user(emailAddress),storageQuota(limit)")
            return await asyncio.to_thread(request.execute)

        about = await self._retry_http(_about)
        self._service_account_email = str(about.get("user", {}).get("emailAddress", ""))
        limit = str(about.get("storageQuota", {}).get("limit", ""))
        if limit == "0":
            sa_email = self._service_account_email or "service-account"
            raise PermissionError(
                "Google Service Account имеет нулевую квоту Drive. "
                "Создайте папку в вашем Google Drive, расшарьте ее на "
                f"{sa_email} как Editor, и укажите GOOGLE_DRIVE_PARENT_FOLDER_ID в .env."
            )

    async def _ensure_template_tabs(
        self,
        *,
        sheet_id: str,
        rename_first_to_dashboard: bool,
    ) -> None:
        async def _get_spreadsheet() -> dict[str, Any]:
            request = self._sheets.spreadsheets().get(
                spreadsheetId=sheet_id,
                fields="sheets(properties(sheetId,title),charts(chartId,position(sheetId)))",
            )
            return await asyncio.to_thread(request.execute)

        metadata = await self._retry_http(_get_spreadsheet)
        sheets = metadata.get("sheets", [])
        titles: set[str] = set()
        first_sheet_id: int | None = None

        for idx, sheet in enumerate(sheets):
            props = sheet.get("properties", {})
            title = str(props.get("title", "")).strip()
            if title:
                titles.add(title)
            if idx == 0 and "sheetId" in props:
                first_sheet_id = int(props["sheetId"])

        requests: list[dict[str, Any]] = []
        required = [
            DASHBOARD_TAB,
            EXPENSES_TAB,
            RAW_EXPENSES_TAB,
            CATEGORIES_TAB,
            USERS_TAB,
            SETTINGS_TAB,
            AUDIT_TAB,
            LEDGER_TAB,
        ]

        if DASHBOARD_TAB not in titles:
            if rename_first_to_dashboard and first_sheet_id is not None:
                requests.append(
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": first_sheet_id, "title": DASHBOARD_TAB},
                            "fields": "title",
                        }
                    }
                )
                titles.add(DASHBOARD_TAB)
            else:
                requests.append({"addSheet": {"properties": {"title": DASHBOARD_TAB}}})
                titles.add(DASHBOARD_TAB)

        for tab in required:
            if tab in titles:
                continue
            requests.append({"addSheet": {"properties": {"title": tab}}})

        if not requests:
            return

        async def _batch_update() -> dict[str, Any]:
            request = self._sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": requests},
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch_update)

    async def _batch_update_values(self, *, sheet_id: str, data: list[dict[str, Any]]) -> None:
        async def _batch() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"valueInputOption": "USER_ENTERED", "data": data},
                )
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch)

    async def _get_spreadsheet_metadata(self, *, sheet_id: str) -> dict[str, int]:
        async def _get() -> dict[str, Any]:
            request = self._sheets.spreadsheets().get(
                spreadsheetId=sheet_id,
                fields="sheets(properties(sheetId,title))",
            )
            return await asyncio.to_thread(request.execute)

        response = await self._retry_http(_get)
        mapping: dict[str, int] = {}
        for sheet in response.get("sheets", []):
            props = sheet.get("properties", {})
            title = str(props.get("title", "")).strip()
            raw_sheet_id = props.get("sheetId")
            if title and raw_sheet_id is not None:
                mapping[title] = int(raw_sheet_id)
        if DASHBOARD_TAB not in mapping:
            raise ValueError("Dashboard sheet not found")
        return mapping

    async def _format_dashboard(self, *, sheet_id: str, dashboard_sheet_id: int) -> None:
        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": dashboard_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 8,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": {"red": 0.12, "green": 0.2, "blue": 0.32}},
                            "horizontalAlignment": "LEFT",
                            "backgroundColorStyle": {"rgbColor": {"red": 0.91, "green": 0.95, "blue": 0.99}},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,horizontalAlignment,backgroundColorStyle)",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": dashboard_sheet_id, "startRowIndex": 2, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 8},
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColorStyle": {"rgbColor": {"red": 0.98, "green": 0.98, "blue": 0.98}},
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColorStyle",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": dashboard_sheet_id, "startRowIndex": 6, "endRowIndex": 7, "startColumnIndex": 0, "endColumnIndex": 2},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColorStyle": {"rgbColor": {"red": 0.95, "green": 0.95, "blue": 0.95}},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColorStyle)",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": dashboard_sheet_id, "startRowIndex": 10, "endRowIndex": 11, "startColumnIndex": 0, "endColumnIndex": 5},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColorStyle": {"rgbColor": {"red": 0.95, "green": 0.95, "blue": 0.95}},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColorStyle)",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": dashboard_sheet_id, "startRowIndex": 17, "endRowIndex": 18, "startColumnIndex": 0, "endColumnIndex": 5},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColorStyle": {"rgbColor": {"red": 0.95, "green": 0.95, "blue": 0.95}},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColorStyle)",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": dashboard_sheet_id, "startRowIndex": 34, "endRowIndex": 35, "startColumnIndex": 0, "endColumnIndex": 5},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColorStyle": {"rgbColor": {"red": 0.95, "green": 0.95, "blue": 0.95}},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColorStyle)",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": dashboard_sheet_id, "startRowIndex": 51, "endRowIndex": 52, "startColumnIndex": 0, "endColumnIndex": 6},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColorStyle": {"rgbColor": {"red": 0.95, "green": 0.95, "blue": 0.95}},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColorStyle)",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": dashboard_sheet_id, "startRowIndex": 11, "endRowIndex": 220, "startColumnIndex": 1, "endColumnIndex": 2},
                    "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}},
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
            {
                "repeatCell": {
                    "range": {"sheetId": dashboard_sheet_id, "startRowIndex": 11, "endRowIndex": 220, "startColumnIndex": 4, "endColumnIndex": 5},
                    "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}},
                    "fields": "userEnteredFormat.numberFormat",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": dashboard_sheet_id, "dimension": "COLUMNS", "startIndex": 0, "endIndex": 1},
                    "properties": {"pixelSize": 230},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": dashboard_sheet_id, "dimension": "COLUMNS", "startIndex": 1, "endIndex": 2},
                    "properties": {"pixelSize": 170},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": dashboard_sheet_id, "dimension": "COLUMNS", "startIndex": 3, "endIndex": 5},
                    "properties": {"pixelSize": 170},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {"sheetId": dashboard_sheet_id, "dimension": "COLUMNS", "startIndex": 7, "endIndex": 9},
                    "properties": {"hiddenByUser": True},
                    "fields": "hiddenByUser",
                }
            },
        ]

        async def _batch() -> dict[str, Any]:
            request = self._sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": requests},
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch)

    async def _set_dashboard_period_validation(
        self,
        *,
        sheet_id: str,
        dashboard_sheet_id: int,
    ) -> None:
        condition_values = [{"userEnteredValue": option} for option in DASHBOARD_PERIOD_OPTIONS]
        request_body = {
            "requests": [
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": dashboard_sheet_id,
                            "startRowIndex": 6,
                            "endRowIndex": 7,
                            "startColumnIndex": 1,
                            "endColumnIndex": 2,
                        },
                        "rule": {
                            "condition": {
                                "type": "ONE_OF_LIST",
                                "values": condition_values,
                            },
                            "inputMessage": "Выберите период для сводки",
                            "strict": True,
                            "showCustomUi": True,
                        },
                    }
                }
            ]
        }

        async def _batch() -> dict[str, Any]:
            request = self._sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body=request_body,
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch)

    async def _rebuild_dashboard_charts(self, *, sheet_id: str, dashboard_sheet_id: int) -> None:
        async def _get() -> dict[str, Any]:
            request = self._sheets.spreadsheets().get(
                spreadsheetId=sheet_id,
                fields="sheets(charts(chartId,position(sheetId)))",
            )
            return await asyncio.to_thread(request.execute)

        metadata = await self._retry_http(_get)
        delete_requests: list[dict[str, Any]] = []
        for sheet in metadata.get("sheets", []):
            for chart in sheet.get("charts", []):
                position = chart.get("position", {})
                if int(position.get("sheetId", -1)) != dashboard_sheet_id:
                    continue
                chart_id = chart.get("chartId")
                if chart_id is None:
                    continue
                delete_requests.append({"deleteEmbeddedObject": {"objectId": int(chart_id)}})

        pie_chart_request = {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Расходы по категориям",
                        "pieChart": {
                            "legendPosition": "RIGHT_LEGEND",
                            "domain": {
                                "sourceRange": {
                                    "sources": [
                                        {
                                            "sheetId": dashboard_sheet_id,
                                            "startRowIndex": 18,
                                            "endRowIndex": 215,
                                            "startColumnIndex": 0,
                                            "endColumnIndex": 1,
                                        }
                                    ]
                                }
                            },
                            "series": {
                                "sourceRange": {
                                    "sources": [
                                        {
                                            "sheetId": dashboard_sheet_id,
                                            "startRowIndex": 18,
                                            "endRowIndex": 215,
                                            "startColumnIndex": 1,
                                            "endColumnIndex": 2,
                                        }
                                    ]
                                }
                            },
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": dashboard_sheet_id,
                                "rowIndex": 17,
                                "columnIndex": 5,
                            },
                            "offsetXPixels": 10,
                            "offsetYPixels": 10,
                            "widthPixels": 520,
                            "heightPixels": 330,
                        }
                    },
                }
            }
        }

        trend_chart_request = {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Динамика расходов по месяцам",
                        "basicChart": {
                            "chartType": "COLUMN",
                            "legendPosition": "NO_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Месяц"},
                                {"position": "LEFT_AXIS", "title": "Сумма"},
                            ],
                            "domains": [
                                {
                                    "domain": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": dashboard_sheet_id,
                                                    "startRowIndex": 18,
                                                    "endRowIndex": 215,
                                                    "startColumnIndex": 3,
                                                    "endColumnIndex": 4,
                                                }
                                            ]
                                        }
                                    }
                                }
                            ],
                            "series": [
                                {
                                    "series": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": dashboard_sheet_id,
                                                    "startRowIndex": 18,
                                                    "endRowIndex": 215,
                                                    "startColumnIndex": 4,
                                                    "endColumnIndex": 5,
                                                }
                                            ]
                                        }
                                    },
                                    "targetAxis": "LEFT_AXIS",
                                }
                            ],
                            "headerCount": 0,
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": dashboard_sheet_id,
                                "rowIndex": 34,
                                "columnIndex": 5,
                            },
                            "offsetXPixels": 10,
                            "offsetYPixels": 10,
                            "widthPixels": 520,
                            "heightPixels": 330,
                        }
                    },
                }
            }
        }

        cashflow_chart_request = {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Пополнения и расходы",
                        "basicChart": {
                            "chartType": "LINE",
                            "legendPosition": "BOTTOM_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "Месяц"},
                                {"position": "LEFT_AXIS", "title": "Сумма"},
                            ],
                            "domains": [
                                {
                                    "domain": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": dashboard_sheet_id,
                                                    "startRowIndex": 52,
                                                    "endRowIndex": 215,
                                                    "startColumnIndex": 0,
                                                    "endColumnIndex": 1,
                                                }
                                            ]
                                        }
                                    }
                                }
                            ],
                            "series": [
                                {
                                    "series": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": dashboard_sheet_id,
                                                    "startRowIndex": 52,
                                                    "endRowIndex": 215,
                                                    "startColumnIndex": 1,
                                                    "endColumnIndex": 2,
                                                }
                                            ]
                                        }
                                    },
                                    "targetAxis": "LEFT_AXIS",
                                },
                                {
                                    "series": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": dashboard_sheet_id,
                                                    "startRowIndex": 52,
                                                    "endRowIndex": 215,
                                                    "startColumnIndex": 2,
                                                    "endColumnIndex": 3,
                                                }
                                            ]
                                        }
                                    },
                                    "targetAxis": "LEFT_AXIS",
                                },
                                {
                                    "series": {
                                        "sourceRange": {
                                            "sources": [
                                                {
                                                    "sheetId": dashboard_sheet_id,
                                                    "startRowIndex": 52,
                                                    "endRowIndex": 215,
                                                    "startColumnIndex": 3,
                                                    "endColumnIndex": 4,
                                                }
                                            ]
                                        }
                                    },
                                    "targetAxis": "LEFT_AXIS",
                                },
                            ],
                            "headerCount": 0,
                        },
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": dashboard_sheet_id,
                                "rowIndex": 51,
                                "columnIndex": 5,
                            },
                            "offsetXPixels": 10,
                            "offsetYPixels": 10,
                            "widthPixels": 520,
                            "heightPixels": 330,
                        }
                    },
                }
            }
        }

        all_requests = [
            *delete_requests,
            pie_chart_request,
            trend_chart_request,
            cashflow_chart_request,
        ]

        async def _batch() -> dict[str, Any]:
            request = self._sheets.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id,
                body={"requests": all_requests},
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch)

    def _build_permission_hint(self, *, folder_id: str | None, http_error: HttpError) -> str:
        if folder_id:
            sa_email = self._service_account_email or "service-account"
            return (
                "Google отказал в создании таблицы (403). "
                "Проверьте, что папка GOOGLE_DRIVE_PARENT_FOLDER_ID существует и расшарена "
                f"на {sa_email} с ролью Editor, и что в Google Cloud включены Sheets API + Drive API."
            )
        return (
            "Google отказал в создании таблицы (403). "
            "Частая причина: у Service Account нулевая квота Drive. "
            "Создайте папку в вашем Google Drive, расшарьте ее на Service Account как Editor, "
            "запишите ID папки в GOOGLE_DRIVE_PARENT_FOLDER_ID и повторите /start."
        )

    async def _retry_http(self, func: Any) -> Any:
        async def _wrapped() -> Any:
            return await func()

        return await retry_async(
            _wrapped,
            max_attempts=self._settings.google_api_retry_max_attempts,
            base_delay=self._settings.google_api_retry_base_delay_seconds,
            max_delay=self._settings.google_api_retry_max_delay_seconds,
            retry_exceptions=(HttpError,),
        )

    async def _read_range(self, *, sheet_id: str, range_name: str) -> list[list[str]]:
        async def _read() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .get(
                    spreadsheetId=sheet_id,
                    range=range_name,
                )
            )
            return await asyncio.to_thread(request.execute)

        result = await self._retry_http(_read)
        return [[str(v) for v in row] for row in result.get("values", [])]

    async def _append_rows(self, *, sheet_id: str, range_name: str, rows: list[list[str]]) -> None:
        async def _append() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .append(
                    spreadsheetId=sheet_id,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": rows},
                )
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_append)

    async def _update_single_cell(self, *, sheet_id: str, range_name: str, value: str) -> None:
        async def _update() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .update(
                    spreadsheetId=sheet_id,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    body={"values": [[value]]},
                )
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_update)

    async def _replace_rows_with_header(
        self,
        *,
        sheet_id: str,
        tab_name: str,
        headers: list[str],
        rows: list[list[str]],
    ) -> None:
        values = [headers, *rows] if rows else [headers]

        async def _clear() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .clear(
                    spreadsheetId=sheet_id,
                    range=f"{tab_name}!A:ZZZ",
                    body={},
                )
            )
            return await asyncio.to_thread(request.execute)

        async def _update() -> dict[str, Any]:
            request = (
                self._sheets.spreadsheets()
                .values()
                .update(
                    spreadsheetId=sheet_id,
                    range=f"{tab_name}!A1",
                    valueInputOption="RAW",
                    body={"values": values},
                )
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_clear)
        await self._retry_http(_update)
