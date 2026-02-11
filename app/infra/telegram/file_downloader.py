import io

from aiogram import Bot


class TelegramFileDownloader:
    def __init__(
        self, *, bot: Bot, max_file_size_bytes: int, download_timeout_seconds: int
    ) -> None:
        self._bot = bot
        self._max_file_size_bytes = max_file_size_bytes
        self._download_timeout_seconds = download_timeout_seconds

    async def download_file(self, file_id: str, expected_file_size: int | None = None) -> bytes:
        if expected_file_size and expected_file_size > self._max_file_size_bytes:
            raise ValueError("File is too large.")
        file = await self._bot.get_file(
            file_id=file_id, request_timeout=self._download_timeout_seconds
        )
        if not file.file_path:
            raise ValueError("Cannot resolve Telegram file path.")
        buf = io.BytesIO()
        await self._bot.download(
            file=file.file_path, destination=buf, timeout=self._download_timeout_seconds
        )
        payload = buf.getvalue()
        if len(payload) > self._max_file_size_bytes:
            raise ValueError("File is too large.")
        return payload
