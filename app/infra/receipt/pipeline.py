from structlog.stdlib import get_logger

from app.domain.entities import ActorContext, ReceiptProcessResult, TelegramPhotoMeta
from app.infra.receipt.providers.base import ReceiptProvider
from app.infra.receipt.qr_decode import QrDecoder
from app.infra.telegram.file_downloader import TelegramFileDownloader
from app.utils.idempotency import sha256_hex
from app.utils.masking import safe_payload_preview

logger = get_logger(__name__)


class ReceiptPipeline:
    def __init__(
        self,
        *,
        downloader: TelegramFileDownloader,
        decoder: QrDecoder,
        provider: ReceiptProvider,
    ) -> None:
        self._downloader = downloader
        self._decoder = decoder
        self._provider = provider

    async def process_photo(
        self, file_meta: TelegramPhotoMeta, actor: ActorContext
    ) -> ReceiptProcessResult:
        image_bytes = await self._downloader.download_file(
            file_id=file_meta.file_id,
            expected_file_size=file_meta.file_size,
        )
        payload = await self._decoder.decode(image_bytes)
        payload_hash = sha256_hex(payload)
        receipt_ref = self._provider.parse(payload)
        items = await self._provider.fetch_items(receipt_ref)
        fallback_required = len(items) == 0

        logger.info(
            "receipt.pipeline.processed",
            actor_telegram_id=actor.telegram_id,
            payload_hash=payload_hash,
            payload_preview=safe_payload_preview(payload),
            fallback_required=fallback_required,
        )

        return ReceiptProcessResult(
            payload_hash=payload_hash,
            payload_preview=safe_payload_preview(payload),
            receipt_ref=receipt_ref,
            items=items,
            fallback_required=fallback_required,
        )
