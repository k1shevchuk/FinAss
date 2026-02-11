import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    retry_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    attempt = 1
    while True:
        try:
            return await func()
        except retry_exceptions:
            if attempt >= max_attempts:
                raise
            backoff = min(max_delay, base_delay * (2 ** (attempt - 1)))
            jitter = backoff * 0.2 * random.random()
            await asyncio.sleep(backoff + jitter)
            attempt += 1
