import asyncio

import cv2
import numpy as np


class QrDecodeError(RuntimeError):
    pass


class QrDecoder:
    def __init__(self, *, max_pixels: int, decode_timeout_seconds: int) -> None:
        self._max_pixels = max_pixels
        self._decode_timeout = decode_timeout_seconds

    async def decode(self, image_bytes: bytes) -> str:
        async def _run() -> str:
            return await asyncio.to_thread(self._decode_sync, image_bytes)

        return await asyncio.wait_for(_run(), timeout=self._decode_timeout)

    def _decode_sync(self, image_bytes: bytes) -> str:
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if image is None:
            raise QrDecodeError("Cannot decode image bytes.")
        pixels = int(image.shape[0] * image.shape[1])
        if pixels > self._max_pixels:
            raise QrDecodeError("Image too large.")
        detector = cv2.QRCodeDetector()
        payload, _, _ = detector.detectAndDecode(image)
        if not payload:
            raise QrDecodeError("QR code not found.")
        return payload.strip()
