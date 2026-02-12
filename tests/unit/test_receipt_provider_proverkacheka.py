from decimal import Decimal

import pytest

from app.domain.entities import ReceiptRef
from app.infra.receipt.providers.proverkacheka import ProverkachekaReceiptProvider


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        _ = (exc_type, exc, tb)

    async def post(self, url: str, data: dict[str, str]) -> _FakeResponse:
        assert url.endswith("/api/v1/check/get")
        assert data["token"] == "test-api-token"  # noqa: S105
        assert "qrraw" in data
        return _FakeResponse(self._payload)


@pytest.mark.asyncio
async def test_proverkacheka_provider_parses_items(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "code": 1,
        "data": {
            "json": {
                "items": [
                    {"name": "Молоко 3.2%", "quantity": 2, "price": 8990, "sum": 17980},
                    {"name": "Хлеб", "quantity": 1, "price": 4590, "sum": 4590},
                ]
            }
        },
    }

    monkeypatch.setattr(
        "app.infra.receipt.providers.proverkacheka.httpx.AsyncClient",
        lambda *args, **kwargs: _FakeClient(payload),
    )
    provider = ProverkachekaReceiptProvider(api_token="test-api-token")  # noqa: S106

    items = await provider.fetch_items(
        ReceiptRef(raw_payload="t=20260211T2310&s=225.70&fn=1&i=2&fp=3&n=1")
    )
    assert len(items) == 2
    assert items[0].name == "Молоко 3.2%"
    assert items[0].quantity == Decimal("2")
    assert items[0].unit_price == Decimal("89.90")
    assert items[0].total_price == Decimal("179.80")


@pytest.mark.asyncio
async def test_proverkacheka_provider_returns_empty_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenClient:
        async def __aenter__(self) -> "_BrokenClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            _ = (exc_type, exc, tb)

        async def post(self, url: str, data: dict[str, str]):  # type: ignore[no-untyped-def]
            _ = (url, data)
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.infra.receipt.providers.proverkacheka.httpx.AsyncClient",
        lambda *args, **kwargs: _BrokenClient(),
    )
    provider = ProverkachekaReceiptProvider(api_token="test-api-token")  # noqa: S106
    items = await provider.fetch_items(
        ReceiptRef(raw_payload="t=20260211T2310&s=225.70&fn=1&i=2&fp=3&n=1")
    )
    assert items == []
