import re
from decimal import Decimal, InvalidOperation

from email_validator import EmailNotValidError, validate_email

EMAIL_MAX_LENGTH = 254
USERNAME_PATTERN = re.compile(r"^@[A-Za-z0-9_]{5,32}$")
SHEET_ID_PATTERN = re.compile(
    r"(?:https?://docs\.google\.com/spreadsheets/d/)?(?P<id>[a-zA-Z0-9-_]{20,})"
)


def is_valid_email(value: str) -> bool:
    if not value or len(value) > EMAIL_MAX_LENGTH:
        return False
    try:
        validate_email(value, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def is_valid_telegram_username(value: str) -> bool:
    return bool(USERNAME_PATTERN.match(value))


def parse_decimal(value: str) -> Decimal:
    normalized = value.replace(",", ".").strip()
    if not normalized:
        raise ValueError("empty decimal")
    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if result < 0:
        raise ValueError("negative value not allowed")
    return result


def extract_google_sheet_id(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    match = SHEET_ID_PATTERN.search(candidate)
    if not match:
        return None
    return match.group("id")
