from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
import pytest
import qrcode

from app.infra.receipt.qr_decode import QrDecodeError, QrDecoder

REAL_RECEIPT_FIXTURE_BYTES = Path("tests/img_test/image.png").read_bytes()


def _make_qr_bytes(payload: str) -> bytes:
    img = qrcode.make(payload)
    from io import BytesIO

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_qr_decoder_success() -> None:
    decoder = QrDecoder(max_pixels=4_000_000, decode_timeout_seconds=3)
    payload = "t=20260211T1910&s=1299.50&fn=9289000100257394"
    image = _make_qr_bytes(payload)
    decoded = await decoder.decode(image)
    assert decoded == payload


@pytest.mark.asyncio
async def test_qr_decoder_no_qr() -> None:
    decoder = QrDecoder(max_pixels=4_000_000, decode_timeout_seconds=3)
    with pytest.raises(QrDecodeError):
        await decoder.decode(b"not-an-image")


def _make_receipt_like_qr_bytes(payload: str) -> bytes:
    height, width = 1200, 640
    image = np.full((height, width, 3), 245, dtype=np.uint8)

    for y in range(30, 1080, 22):
        color = int(90 + (y % 20))
        cv2.line(image, (20, y), (width - 60, y), (color, color, color), 1)

    qr = qrcode.QRCode(border=1, box_size=4)
    qr.add_data(payload)
    qr.make(fit=True)
    qr_image = np.array(qr.make_image(fill_color="black", back_color="white").convert("RGB"))
    qr_small = cv2.resize(qr_image, (96, 96), interpolation=cv2.INTER_AREA)

    y0 = height - 96 - 24
    x0 = width - 96 - 18
    image[y0 : y0 + 96, x0 : x0 + 96] = qr_small

    image = cast(np.ndarray[Any, Any], cv2.GaussianBlur(image, (3, 3), 1.1))
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        raise RuntimeError("Failed to encode test image.")
    return encoded.tobytes()


@pytest.mark.asyncio
async def test_qr_decoder_receipt_like_image() -> None:
    decoder = QrDecoder(max_pixels=12_000_000, decode_timeout_seconds=5)
    payload = "t=20260211T1910&s=4199.00&fn=99604400502798330&i=254016706"
    image = _make_receipt_like_qr_bytes(payload)
    decoded = await decoder.decode(image)
    assert decoded == payload


@pytest.mark.asyncio
async def test_qr_decoder_real_receipt_fixture() -> None:
    decoder = QrDecoder(max_pixels=12_000_000, decode_timeout_seconds=8)
    decoded = await decoder.decode(REAL_RECEIPT_FIXTURE_BYTES)
    assert decoded.startswith("t=20230502T2022")
