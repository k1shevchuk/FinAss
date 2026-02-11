import pytest
import qrcode

from app.infra.receipt.qr_decode import QrDecodeError, QrDecoder


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
