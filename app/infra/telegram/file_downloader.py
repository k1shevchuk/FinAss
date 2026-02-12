import asyncio
import io

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter


class TelegramFileDownloader:
    def __init__(
        self, *, bot: Bot, max_file_size_bytes: int, download_timeout_seconds: int
    ) -> None:
        self._bot = bot
        self._max_file_size_bytes = max_file_size_bytes
        self._download_timeout_seconds = download_timeout_seconds
        self._max_attempts = 3

    async def download_file(self, file_id: str, expected_file_size: int | None = None) -> bytes:
        if expected_file_size and expected_file_size > self._max_file_size_bytes:
            raise ValueError("Файл слишком большой. Отправьте изображение меньше 5 MB.")

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                file = await self._bot.get_file(
                    file_id=file_id, request_timeout=self._download_timeout_seconds
                )
                if not file.file_path:
                    raise ValueError("Не удалось получить путь к файлу в Telegram.")

                buf = io.BytesIO()
                await self._bot.download_file(
                    file_path=file.file_path,
                    destination=buf,
                    timeout=self._download_timeout_seconds,
                )
                payload = buf.getvalue()
                if len(payload) > self._max_file_size_bytes:
                    raise ValueError("Файл слишком большой. Отправьте изображение меньше 5 MB.")
                return payload
            except TelegramRetryAfter as exc:
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                await asyncio.sleep(max(0.5, float(exc.retry_after)))
            except TelegramNetworkError as exc:
                last_error = exc
                if attempt >= self._max_attempts:
                    break
                await asyncio.sleep(0.4 * (2 ** (attempt - 1)))
            except TelegramBadRequest as exc:
                last_error = exc
                message = str(exc).casefold()
                is_transient = "temporarily unavailable" in message
                is_wrong_file = "wrong file_id" in message
                if is_transient and attempt < self._max_attempts:
                    await asyncio.sleep(0.4 * (2 ** (attempt - 1)))
                    continue
                if is_transient or is_wrong_file:
                    raise ValueError(
                        "Не удалось получить фото из Telegram. "
                        "Отправьте фото еще раз, лучше как файл (без сжатия)."
                    ) from exc
                raise

        raise ValueError("Не удалось скачать изображение из Telegram. Попробуйте еще раз.") from last_error
