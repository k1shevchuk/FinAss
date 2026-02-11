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
        payload = self._decode_with_variants(detector=detector, image=image)
        if not payload:
            raise QrDecodeError("QR code not found.")
        return payload.strip()

    def _decode_with_variants(self, *, detector: cv2.QRCodeDetector, image: np.ndarray) -> str:
        variants = self._prepare_variants(image)
        for candidate in variants:
            payload = self._detect_payload(detector=detector, image=candidate)
            if payload:
                return payload
        return ""

    @staticmethod
    def _detect_payload(*, detector: cv2.QRCodeDetector, image: np.ndarray) -> str:
        payload, _, _ = detector.detectAndDecode(image)
        if payload:
            return payload.strip()
        ok, payloads, _, _ = detector.detectAndDecodeMulti(image)
        if ok:
            for item in payloads:
                if item:
                    return item.strip()
        return ""

    @staticmethod
    def _prepare_variants(image: np.ndarray) -> list[np.ndarray]:
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, binary_otsu = cv2.threshold(grayscale, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(
            grayscale,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            2,
        )

        base_variants: list[np.ndarray] = [image, grayscale, binary_otsu, adaptive]
        rotated: list[np.ndarray] = []
        for item in base_variants:
            rotated.append(item)
            rotated.append(cv2.rotate(item, cv2.ROTATE_90_CLOCKWISE))
            rotated.append(cv2.rotate(item, cv2.ROTATE_180))
            rotated.append(cv2.rotate(item, cv2.ROTATE_90_COUNTERCLOCKWISE))

        scaled: list[np.ndarray] = []
        for item in rotated:
            scaled.append(item)
            scaled.append(cv2.resize(item, dsize=None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC))
            scaled.append(cv2.resize(item, dsize=None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC))
        return scaled
