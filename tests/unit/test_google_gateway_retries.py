import httplib2
import pytest
from googleapiclient.errors import HttpError

from app.domain.entities import ExpenseRow
from app.infra.google.sheets_gateway import GoogleSheetsGateway


class DummyDriveSharing:
    async def share_spreadsheet(self, sheet_id: str, email: str, role: str = "writer") -> None:
        _ = (sheet_id, email, role)


class DummySettings:
    google_api_retry_max_attempts = 5
    google_api_retry_base_delay_seconds = 0.01
    google_api_retry_max_delay_seconds = 0.05


@pytest.mark.asyncio
async def test_gateway_retries_http_error() -> None:
    gateway = GoogleSheetsGateway(
        sheets_service=object(),
        drive_sharing=DummyDriveSharing(),  # type: ignore[arg-type]
        settings=DummySettings(),  # type: ignore[arg-type]
    )
    attempts = {"count": 0}

    async def flaky() -> dict[str, str]:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise HttpError(resp=httplib2.Response({"status": "429"}), content=b"rate limited")
        return {"ok": "true"}

    result = await gateway._retry_http(flaky)
    assert result == {"ok": "true"}
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_append_expenses_repairs_tabs_on_400(mocker) -> None:  # type: ignore[no-untyped-def]
    gateway = GoogleSheetsGateway(
        sheets_service=object(),
        drive_sharing=DummyDriveSharing(),  # type: ignore[arg-type]
        settings=DummySettings(),  # type: ignore[arg-type]
    )
    attempts = {"count": 0}

    async def fake_retry(func: object) -> dict[str, object]:
        _ = func
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise HttpError(resp=httplib2.Response({"status": "400"}), content=b"bad range")
        return {"updates": {"updatedRows": 1}}

    repair_mock = mocker.AsyncMock()
    mocker.patch.object(gateway, "_retry_http", side_effect=fake_retry)
    mocker.patch.object(gateway, "_repair_expenses_tabs", repair_mock)

    result = await gateway.append_expenses(
        sheet_id="sheet-id",
        rows=[ExpenseRow(values=["1"])],
    )
    assert result.updated_rows == 1
    assert attempts["count"] == 2
    repair_mock.assert_awaited_once_with(sheet_id="sheet-id")
