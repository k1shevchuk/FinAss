from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs

from app.domain.entities import ReceiptItem, ReceiptRef
from app.infra.receipt.providers.base import ReceiptProvider


class FallbackReceiptProvider(ReceiptProvider):
    def parse(self, payload: str) -> ReceiptRef:
        # Supports generic "k=v&k=v" payload and common receipt QR keys.
        parsed = parse_qs(payload, keep_blank_values=True)
        total: Decimal | None = None
        purchased_at: datetime | None = None
        merchant: str | None = None
        currency: str | None = None

        if "s" in parsed and parsed["s"]:
            try:
                total = Decimal(parsed["s"][0].replace(",", "."))
            except Exception:
                total = None

        if "t" in parsed and parsed["t"]:
            # Common format: YYYYMMDDTHHMM
            raw_t = parsed["t"][0]
            try:
                purchased_at = datetime.strptime(raw_t[:13], "%Y%m%dT%H%M")
            except Exception:
                purchased_at = None

        if "m" in parsed and parsed["m"]:
            merchant = parsed["m"][0]
        if "currency" in parsed and parsed["currency"]:
            currency = parsed["currency"][0]

        return ReceiptRef(
            raw_payload=payload,
            total=total,
            purchased_at=purchased_at,
            merchant=merchant,
            currency=currency,
        )

    async def fetch_items(self, ref: ReceiptRef) -> list[ReceiptItem]:
        # v1 fallback only: external item providers are not connected.
        return []
