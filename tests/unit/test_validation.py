from app.utils.masking import mask_email
from app.utils.validation import extract_google_sheet_id, is_valid_email, parse_decimal


def test_email_validation() -> None:
    assert is_valid_email("name@gmail.com")
    assert not is_valid_email("invalid")
    assert not is_valid_email("")


def test_masking() -> None:
    assert mask_email("kirill@gmail.com").startswith("k***@g***")


def test_parse_decimal() -> None:
    assert str(parse_decimal("10.5")) == "10.5"
    assert str(parse_decimal("10,5")) == "10.5"


def test_extract_google_sheet_id() -> None:
    sheet_id = "1AbCdEfGhIjKlMnOpQrStUvWxYz_1234567890"
    link = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid=0"
    assert extract_google_sheet_id(link) == sheet_id
    assert extract_google_sheet_id(sheet_id) == sheet_id
    assert extract_google_sheet_id("not a sheet") is None
