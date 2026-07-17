from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 5,
    base_delay: float = 1.0,
    logger: logging.Logger | None = None,
) -> T:
    """以 1s, 2s, 4s, 8s 指數退避重試非同步操作。"""

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            delay = base_delay * (2**attempt)
            if logger:
                logger.warning("操作失敗，%.0f 秒後重試 (%s/%s): %s", delay, attempt + 1, attempts, exc)
            await asyncio.sleep(delay)
    raise last_error or RuntimeError("Retry operation failed without an exception.")
