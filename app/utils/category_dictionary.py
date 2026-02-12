import json
from pathlib import Path

from app.domain.entities import CategoryRule

_CATEGORY_FILE_PATH = Path(__file__).resolve().parents[1] / "data" / "category_keywords.json"
_cached_mtime_ns: int | None = None
_cached_rules: list[CategoryRule] | None = None


def _fallback_rules() -> list[CategoryRule]:
    return [
        CategoryRule(category="Продукты", keywords=["еда", "food", "grocery", "молоко", "хлеб"]),
        CategoryRule(category="Транспорт", keywords=["taxi", "такси", "bus", "metro", "бензин"]),
        CategoryRule(category="Дом", keywords=["house", "home", "ikea", "ремонт"]),
        CategoryRule(category="Здоровье", keywords=["аптека", "лекар", "doctor", "pharmacy"]),
        CategoryRule(category="Кафе и рестораны", keywords=["кафе", "coffee", "restaurant"]),
        CategoryRule(category="Подписки", keywords=["subscription", "netflix", "spotify"]),
        CategoryRule(category="Одежда", keywords=["одеж", "clothes", "shoes"]),
        CategoryRule(category="Развлечения", keywords=["кино", "cinema", "game"]),
        CategoryRule(category="Другое", keywords=[], enabled=True),
    ]


def load_default_category_rules() -> list[CategoryRule]:
    global _cached_mtime_ns
    global _cached_rules

    current_mtime_ns: int | None
    try:
        current_mtime_ns = _CATEGORY_FILE_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        current_mtime_ns = None

    if (
        _cached_rules is not None
        and _cached_mtime_ns is not None
        and current_mtime_ns is not None
        and _cached_mtime_ns == current_mtime_ns
    ):
        return [
            CategoryRule(category=item.category, keywords=list(item.keywords), enabled=item.enabled)
            for item in _cached_rules
        ]

    try:
        payload = json.loads(_CATEGORY_FILE_PATH.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        fallback = _fallback_rules()
        _cached_rules = fallback
        _cached_mtime_ns = current_mtime_ns
        return [
            CategoryRule(category=item.category, keywords=list(item.keywords), enabled=item.enabled)
            for item in fallback
        ]

    if isinstance(payload, list):
        raw_categories = payload
    elif isinstance(payload, dict):
        raw_categories = payload.get("categories", [])
    else:
        raw_categories = []
    parsed: list[CategoryRule] = []
    for item in raw_categories:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category", "")).strip()
        if not category:
            continue
        raw_keywords = item.get("keywords", [])
        keywords = [
            str(keyword).strip()
            for keyword in raw_keywords
            if isinstance(keyword, str) and str(keyword).strip()
        ]
        enabled = bool(item.get("enabled", True))
        parsed.append(CategoryRule(category=category, keywords=keywords, enabled=enabled))
    result = parsed or _fallback_rules()
    _cached_rules = result
    _cached_mtime_ns = current_mtime_ns
    return [
        CategoryRule(category=item.category, keywords=list(item.keywords), enabled=item.enabled)
        for item in result
    ]


def category_dictionary_version() -> str:
    try:
        return str(_CATEGORY_FILE_PATH.stat().st_mtime_ns)
    except FileNotFoundError:
        return "0"
