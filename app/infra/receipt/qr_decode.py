import asyncio

import cv2
import numpy as np

try:
    import zxingcpp
except Exception:  # noqa: BLE001
    zxingcpp = None  # type: ignore[assignment]


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
        payload = self._detect_payload(detector=detector, image=image)
        if payload:
            return payload.strip()
        payload = self._decode_with_zxing(image=image)
        if payload:
            return payload.strip()
        payload = self._decode_with_regions(detector=detector, image=image)
        if not payload:
            payload = self._decode_with_zxing_regions(image=image)
        if not payload:
            raise QrDecodeError("QR code not found.")
        return payload.strip()

    def _decode_with_regions(self, *, detector: cv2.QRCodeDetector, image: np.ndarray) -> str:
        for region in self._regions_for_search(image):
            for candidate in self._prepare_variants(region):
                payload = self._detect_payload(detector=detector, image=candidate)
                if payload:
                    return payload
        return ""

    def _decode_with_zxing_regions(self, *, image: np.ndarray) -> str:
        for region in self._regions_for_search(image):
            payload = self._decode_with_zxing(image=region)
            if payload:
                return payload
            # Tiny QR in receipt corner often requires explicit upscaling.
            for scale in (2.0, 3.0, 4.0, 5.0):
                upscaled = cv2.resize(
                    region,
                    dsize=None,
                    fx=scale,
                    fy=scale,
                    interpolation=cv2.INTER_CUBIC,
                )
                payload = self._decode_with_zxing(image=upscaled)
                if payload:
                    return payload
        return ""

    @staticmethod
    def _decode_with_zxing(*, image: np.ndarray) -> str:
        if zxingcpp is None:
            return ""
        try:
            result = zxingcpp.read_barcode(image)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            return ""
        if result and getattr(result, "text", ""):
            return str(result.text).strip()
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
    def _regions_for_search(image: np.ndarray) -> list[np.ndarray]:
        h, w = image.shape[:2]
        regions: list[np.ndarray] = [image]

        # Typical receipt QR lives near bottom-right.
        cuts = [
            (0.50, 0.50),
            (0.58, 0.52),
            (0.65, 0.58),
            (0.72, 0.62),
            (0.78, 0.68),
        ]
        for y_ratio, x_ratio in cuts:
            y = int(h * y_ratio)
            x = int(w * x_ratio)
            if y < h - 8 and x < w - 8:
                regions.append(image[y:, x:])

        # Fallback for uncommon layout.
        regions.append(image[h // 2 :, :])
        regions.append(image[:, w // 2 :])
        regions.append(image[h // 2 :, w // 2 :])
        return regions

    @staticmethod
    def _prepare_variants(image: np.ndarray) -> list[np.ndarray]:
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(grayscale)
        _, binary_otsu = cv2.threshold(grayscale, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            2,
        )
        median = cv2.medianBlur(enhanced, 3)

        base_variants: list[np.ndarray] = [image, grayscale, enhanced, binary_otsu, adaptive, median]
        min_dim = min(image.shape[:2])
        scales = [1.0, 2.0, 3.0]
        if min_dim <= 220:
            scales.extend([4.0, 5.0])

        scaled: list[np.ndarray] = []
        for item in base_variants:
            for factor in scales:
                if factor == 1.0:
                    scaled.append(item)
                else:
                    scaled.append(
                        cv2.resize(
                            item,
                            dsize=None,
                            fx=factor,
                            fy=factor,
                            interpolation=cv2.INTER_CUBIC,
                        )
                    )
        return scaled
