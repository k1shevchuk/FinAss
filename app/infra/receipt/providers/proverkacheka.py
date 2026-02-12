from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qs

import httpx
from structlog.stdlib import get_logger

from app.domain.entities import ReceiptItem, ReceiptRef
from app.infra.receipt.providers.fallback import FallbackReceiptProvider

logger = get_logger(__name__)


class ProverkachekaReceiptProvider(FallbackReceiptProvider):
    def __init__(
        self,
        *,
        api_token: str,
        base_url: str = "https://proverkacheka.com",
        timeout_seconds: int = 15,
    ) -> None:
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def fetch_items(self, ref: ReceiptRef) -> list[ReceiptItem]:
        params = _parse_payload_params(ref.raw_payload)
        if not params:
            return []

        endpoint = f"{self._base_url}/api/v1/check/get"
        payload: dict[str, str] = {"token": self._api_token, "qrraw": ref.raw_payload}
        payload.update(params)

        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(endpoint, data=payload)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "receipt.proverkacheka.request_failed",
                error=str(exc),
            )
            return []

        raw_items = _extract_items(body)
        parsed_items: list[ReceiptItem] = []
        for raw_item in raw_items:
            item = _parse_item(raw_item)
            if item is None:
                continue
            parsed_items.append(item)

        logger.info(
            "receipt.proverkacheka.items_parsed",
            items_count=len(parsed_items),
            has_items=bool(parsed_items),
        )
        return parsed_items


def _parse_payload_params(payload: str) -> dict[str, str]:
    parsed = parse_qs(payload, keep_blank_values=False)
    out: dict[str, str] = {}
    for key in ("t", "s", "fn", "i", "fp", "n"):
        values = parsed.get(key)
        if not values:
            continue
        out[key] = str(values[0])
    return out


def _extract_items(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []

    data = body.get("data")
    if not isinstance(data, dict):
        return []

    receipt_json = data.get("json")
    if isinstance(receipt_json, dict):
        items = receipt_json.get("items")
        if isinstance(items, list):
            return [i for i in items if isinstance(i, dict)]

    # Defensive fallback for providers with alternative response envelope.
    ticket = data.get("ticket")
    if isinstance(ticket, dict):
        document = ticket.get("document")
        if isinstance(document, dict):
            receipt = document.get("receipt")
            if isinstance(receipt, dict):
                items = receipt.get("items")
                if isinstance(items, list):
                    return [i for i in items if isinstance(i, dict)]
    return []


def _parse_item(item: dict[str, Any]) -> ReceiptItem | None:
    name = str(item.get("name", "")).strip()
    if not name:
        return None
    quantity = _parse_quantity(item.get("quantity"))
    if quantity <= Decimal("0"):
        quantity = Decimal("1")

    total_price = _parse_money(item.get("sum"))
    unit_price = _parse_money(item.get("price"))

    if total_price <= Decimal("0") and unit_price > Decimal("0"):
        total_price = (unit_price * quantity).quantize(Decimal("0.01"))
    if unit_price <= Decimal("0") and total_price > Decimal("0"):
        unit_price = (total_price / quantity).quantize(Decimal("0.01"))
    if total_price <= Decimal("0") and unit_price <= Decimal("0"):
        return None

    return ReceiptItem(
        name=name,
        quantity=quantity,
        unit_price=unit_price,
        total_price=total_price,
        category="Другое",
    )


def _parse_money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, int):
        return (Decimal(value) / Decimal("100")).quantize(Decimal("0.01"))
    if isinstance(value, float):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    text = str(value).strip().replace(",", ".")
    if not text:
        return Decimal("0")
    try:
        if "." not in text and text.isdigit():
            return (Decimal(text) / Decimal("100")).quantize(Decimal("0.01"))
        return Decimal(text).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_quantity(value: Any) -> Decimal:
    if value is None:
        return Decimal("1")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", ".")
    if not text:
        return Decimal("1")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("1")
