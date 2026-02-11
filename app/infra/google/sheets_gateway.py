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
    CATEGORIES_HEADERS,
    DASHBOARD_VALUES,
    EXPENSES_HEADERS,
    SETTINGS_HEADERS,
    USERS_HEADERS,
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
        title = f"Expense Tracker - {owner.display_name}"
        folder_id = (self._settings.google_drive_parent_folder_id or "").strip() or None

        try:
            if folder_id:
                spreadsheet = await self._create_spreadsheet_in_folder(
                    title=title,
                    folder_id=folder_id,
                )
                await self._ensure_template_tabs(
                    sheet_id=spreadsheet.sheet_id,
                    rename_first_to_dashboard=True,
                )
            else:
                await self._assert_can_create_in_service_account_drive()
                spreadsheet = await self._create_spreadsheet_in_service_account_drive(title=title)

            await self._write_template(sheet_id=spreadsheet.sheet_id, owner=owner)
            await self.share_spreadsheet(
                sheet_id=spreadsheet.sheet_id,
                email=owner.google_share_email,
                role="writer",
            )
            return spreadsheet
        except PermissionError:
            raise
        except HttpError as exc:
            raise PermissionError(
                self._build_permission_hint(folder_id=folder_id, http_error=exc)
            ) from exc

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
                    range="expenses!A1",
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
                    range="audit!A1",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
            )
            return await asyncio.to_thread(request.execute)

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
                    range="users!A1",
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
                .get(spreadsheetId=sheet_id, range="categories!A2:C")
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
                .get(spreadsheetId=sheet_id, range="settings!A2:B")
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
            rows = await self._read_range(sheet_id=sheet_id, range_name="settings!A2:B")
            row_index = 2
            for row in rows:
                if len(row) > 0 and str(row[0]) == key:
                    break
                row_index += 1
            await self._update_single_cell(
                sheet_id=sheet_id,
                range_name=f"settings!B{row_index}",
                value=value,
            )
            return
        await self._append_rows(sheet_id=sheet_id, range_name="settings!A1", rows=[[key, value]])

    async def add_category(self, *, sheet_id: str, category: str, keywords: list[str]) -> None:
        await self._append_rows(
            sheet_id=sheet_id,
            range_name="categories!A1",
            rows=[[category, ", ".join(keywords), "true"]],
        )

    async def set_category_enabled(self, *, sheet_id: str, category: str, enabled: bool) -> bool:
        rows = await self._read_range(sheet_id=sheet_id, range_name="categories!A2:C")
        row_index = 2
        for row in rows:
            if len(row) > 0 and str(row[0]).strip() == category:
                await self._update_single_cell(
                    sheet_id=sheet_id,
                    range_name=f"categories!C{row_index}",
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
                .get(spreadsheetId=sheet_id, range="expenses!A1:R")
            )
            return await asyncio.to_thread(request.execute)

        result = await self._retry_http(_read)
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

    async def _write_template(self, *, sheet_id: str, owner: OwnerContext) -> None:
        headers_body = {
            "valueInputOption": "RAW",
            "data": [
                {"range": "dashboard!A1:B1", "values": [["Expense Tracker Dashboard", ""]]},
                {"range": "expenses!A1:R1", "values": [EXPENSES_HEADERS]},
                {"range": "categories!A1:C1", "values": [CATEGORIES_HEADERS]},
                {"range": "users!A1:D1", "values": [USERS_HEADERS]},
                {"range": "settings!A1:B1", "values": [SETTINGS_HEADERS]},
                {"range": "audit!A1:D1", "values": [AUDIT_HEADERS]},
            ],
        }

        async def _batch_headers() -> dict[str, Any]:
            request = self._sheets.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body=headers_body,
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_batch_headers)
        await self._write_dashboard(sheet_id=sheet_id)
        await self._ensure_default_categories(sheet_id=sheet_id)
        await self._ensure_owner_row(sheet_id=sheet_id, owner=owner)
        await self._ensure_default_settings(sheet_id=sheet_id, owner=owner)

    async def _write_dashboard(self, *, sheet_id: str) -> None:
        async def _clear() -> dict[str, Any]:
            request = self._sheets.spreadsheets().values().clear(
                spreadsheetId=sheet_id,
                range="dashboard!A1:Z100",
                body={},
            )
            return await asyncio.to_thread(request.execute)

        await self._retry_http(_clear)
        await self._append_rows(
            sheet_id=sheet_id,
            range_name="dashboard!A1",
            rows=DASHBOARD_VALUES,
        )

    async def _ensure_default_categories(self, *, sheet_id: str) -> None:
        rows = await self._read_range(sheet_id=sheet_id, range_name="categories!A2:C")
        if rows:
            return
        rows_categories = [
            [item.category, ", ".join(item.keywords), "true" if item.enabled else "false"]
            for item in default_categories()
        ]
        await self._append_rows(
            sheet_id=sheet_id,
            range_name="categories!A1",
            rows=rows_categories,
        )

    async def _ensure_owner_row(self, *, sheet_id: str, owner: OwnerContext) -> None:
        rows = await self._read_range(sheet_id=sheet_id, range_name="users!A2:D")
        owner_id = str(owner.telegram_id)
        for row in rows:
            if len(row) > 0 and str(row[0]).strip() == owner_id:
                return
        await self._append_rows(
            sheet_id=sheet_id,
            range_name="users!A1",
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
        }
        for key, value in defaults.items():
            if key in settings:
                continue
            await self._append_rows(
                sheet_id=sheet_id,
                range_name="settings!A1",
                rows=[[key, value]],
            )

    async def _create_spreadsheet_in_service_account_drive(self, *, title: str) -> SpreadsheetInfo:
        body = {
            "properties": {"title": title},
            "sheets": [
                {"properties": {"title": "dashboard"}},
                {"properties": {"title": "expenses"}},
                {"properties": {"title": "categories"}},
                {"properties": {"title": "users"}},
                {"properties": {"title": "settings"}},
                {"properties": {"title": "audit"}},
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
        sheet_url = str(created.get("webViewLink") or f"https://docs.google.com/spreadsheets/d/{sheet_id}")
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
                fields="sheets(properties(sheetId,title))",
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
        required = ["dashboard", "expenses", "categories", "users", "settings", "audit"]

        if "dashboard" not in titles:
            if rename_first_to_dashboard and first_sheet_id is not None:
                requests.append(
                    {
                        "updateSheetProperties": {
                            "properties": {"sheetId": first_sheet_id, "title": "dashboard"},
                            "fields": "title",
                        }
                    }
                )
                titles.add("dashboard")
            else:
                requests.append({"addSheet": {"properties": {"title": "dashboard"}}})
                titles.add("dashboard")

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
