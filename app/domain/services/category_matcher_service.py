import re
import time

from app.domain.entities import CategoryRule
from app.domain.services.category_service import CategoryService

_NON_WORD_RE = re.compile(r"[^\w]+", re.UNICODE)


class CategoryMatcherService:
    def __init__(self, *, category_service: CategoryService, cache_ttl_seconds: int = 300) -> None:
        self._category_service = category_service
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[int, tuple[float, list[CategoryRule]]] = {}

    async def match(self, *, actor_id: int, text: str) -> str | None:
        normalized_text = self._normalize(text)
        if not normalized_text:
            return None

        rules = await self._merged_rules(actor_id=actor_id)
        best_category: str | None = None
        best_score = 0
        for rule in rules:
            if not rule.enabled:
                continue
            for keyword in rule.keywords:
                normalized_keyword = self._normalize(keyword)
                if not normalized_keyword:
                    continue
                if normalized_keyword not in normalized_text:
                    continue
                score = (normalized_text.count(normalized_keyword) * 100) + len(normalized_keyword)
                if score > best_score:
                    best_score = score
                    best_category = rule.category
        return best_category

    def invalidate(self, *, actor_id: int) -> None:
        self._cache.pop(actor_id, None)

    async def _merged_rules(self, *, actor_id: int) -> list[CategoryRule]:
        now = time.monotonic()
        cached = self._cache.get(actor_id)
        if cached and cached[0] > now:
            return cached[1]
        merged = await self._category_service.list_categories(actor_id)
        self._cache[actor_id] = (now + self._cache_ttl_seconds, merged)
        return merged

    @staticmethod
    def _normalize(value: str) -> str:
        lowered = value.casefold().strip()
        return " ".join(token for token in _NON_WORD_RE.split(lowered) if token)
