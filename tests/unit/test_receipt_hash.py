from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.utils.idempotency import build_receipt_hash


def test_receipt_hash_deterministic() -> None:
    dt = datetime(2026, 2, 11, 18, 10, tzinfo=ZoneInfo("Europe/Moscow"))
    h1 = build_receipt_hash(payload="abc", local_dt=dt, total=Decimal("100.00"), currency="RUB")
    h2 = build_receipt_hash(payload="abc", local_dt=dt, total=Decimal("100.00"), currency="RUB")
    assert h1 == h2
