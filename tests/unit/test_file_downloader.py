import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import GetFile

from app.infra.telegram.file_downloader import TelegramFileDownloader


class _AlwaysBadRequestBot:
    def __init__(self) -> None:
        self.calls = 0

    async def get_file(self, file_id: str, request_timeout: int):  # noqa: ARG002
        self.calls += 1
        raise TelegramBadRequest(
            method=GetFile(file_id=file_id),
            message="wrong file_id or the file is temporarily unavailable",
        )

    async def download_file(self, file_path: str, destination, **kwargs):  # noqa: ARG002, ANN001
        return None


@pytest.mark.asyncio
async def test_file_downloader_maps_telegram_bad_request_to_user_error() -> None:
    bot = _AlwaysBadRequestBot()
    downloader = TelegramFileDownloader(
        bot=bot,  # type: ignore[arg-type]
        max_file_size_bytes=5 * 1024 * 1024,
        download_timeout_seconds=10,
    )

    with pytest.raises(ValueError):
        await downloader.download_file(file_id="bad-file", expected_file_size=1024)

    assert bot.calls == 3


@pytest.mark.asyncio
async def test_file_downloader_rejects_large_file_early() -> None:
    bot = _AlwaysBadRequestBot()
    downloader = TelegramFileDownloader(
        bot=bot,  # type: ignore[arg-type]
        max_file_size_bytes=100,
        download_timeout_seconds=10,
    )
    with pytest.raises(ValueError):
        await downloader.download_file(file_id="id", expected_file_size=101)
    assert bot.calls == 0
