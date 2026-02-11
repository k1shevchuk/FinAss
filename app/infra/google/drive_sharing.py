from typing import Any

from googleapiclient.errors import HttpError

from app.utils.retry import retry_async


class DriveSharing:
    def __init__(
        self,
        *,
        drive_service: Any,
        max_attempts: int,
        base_delay: float,
        max_delay: float,
    ) -> None:
        self._drive: Any = drive_service
        self._max_attempts = max_attempts
        self._base_delay = base_delay
        self._max_delay = max_delay

    async def share_spreadsheet(self, sheet_id: str, email: str, role: str = "writer") -> None:
        async def _do() -> None:
            request = self._drive.permissions().create(
                fileId=sheet_id,
                sendNotificationEmail=True,
                body={"type": "user", "role": role, "emailAddress": email},
            )
            await _execute(request)

        await retry_async(
            _do,
            max_attempts=self._max_attempts,
            base_delay=self._base_delay,
            max_delay=self._max_delay,
            retry_exceptions=(HttpError,),
        )


async def _execute(request: Any) -> Any:
    import asyncio

    return await asyncio.to_thread(request.execute)
