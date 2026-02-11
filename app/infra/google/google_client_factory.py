from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config.settings import Settings

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleClientFactory:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._credentials = service_account.Credentials.from_service_account_file(
            str(settings.google_credentials_path),
            scopes=list(set(SHEETS_SCOPES + DRIVE_SCOPES)),
        )

    def build_sheets_service(self) -> Any:
        return build("sheets", "v4", credentials=self._credentials, cache_discovery=False)

    def build_drive_service(self) -> Any:
        return build("drive", "v3", credentials=self._credentials, cache_discovery=False)
