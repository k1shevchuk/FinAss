import hashlib
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_receipt_hash(
    *,
    payload: str,
    local_dt: datetime,
    total: Decimal,
    currency: str,
    bucket_minutes: int = 5,
) -> str:
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=ZoneInfo("UTC"))
    minute_bucket = (local_dt.minute // bucket_minutes) * bucket_minutes
    bucket_dt = local_dt.replace(minute=minute_bucket, second=0, microsecond=0).isoformat()
    normalized = "|".join(
        [
            payload.strip(),
            bucket_dt,
            f"{total:.2f}",
            currency.upper().strip(),
        ]
    )
    return sha256_hex(normalized)


def hash_invite_code(code: str, pepper: str) -> str:
    return sha256_hex(f"{pepper}:{code}")
