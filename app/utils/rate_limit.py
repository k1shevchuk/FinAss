from dataclasses import dataclass
from typing import Final

from redis.asyncio import Redis


@dataclass(frozen=True)
class LimitWindow:
    key: str
    limit: int
    ttl_seconds: int


class RedisRateLimiter:
    _PREFIX: Final[str] = "ratelimit"

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, window: LimitWindow) -> bool:
        redis_key = f"{self._PREFIX}:{window.key}"
        value = await self._redis.incr(redis_key)
        if value == 1:
            await self._redis.expire(redis_key, window.ttl_seconds)
        return bool(value <= window.limit)
