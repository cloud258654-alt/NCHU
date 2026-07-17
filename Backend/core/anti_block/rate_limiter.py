from __future__ import annotations

import asyncio
import time
from collections import defaultdict

from core.anti_block.crawl_policy import CrawlPolicy
from core.anti_block.delay_strategy import DelayStrategy
from core.logger import get_logger


class RateLimiter:
    """Per-platform rate limiter that enforces policy delays before actions."""

    def __init__(self, policy: CrawlPolicy | None = None) -> None:
        self.policy = policy or CrawlPolicy.load()
        self._last_acquired_at: dict[str, float] = defaultdict(float)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.logger = get_logger("anti_block.rate_limiter")

    async def acquire(self, platform: str, action: str = "request") -> float:
        async with self._locks[platform]:
            platform_policy = self.policy.for_platform(platform)
            randomized_delay = DelayStrategy.next_delay(platform_policy)
            elapsed = time.monotonic() - self._last_acquired_at[platform]
            wait_seconds = max(0.0, randomized_delay - elapsed)
            if wait_seconds > 0:
                self.logger.info(
                    "Policy delay: platform=%s action=%s wait_seconds=%.2f",
                    platform,
                    action,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
            self._last_acquired_at[platform] = time.monotonic()
            return wait_seconds

