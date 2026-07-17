from __future__ import annotations

import random

from core.anti_block.crawl_policy import PlatformPolicy


class DelayStrategy:
    """Randomized compliant delays. This does not hide identity or bypass controls."""

    MIN_ALLOWED_DELAY = 0.5

    @staticmethod
    def next_delay(policy: PlatformPolicy) -> float:
        min_delay = max(DelayStrategy.MIN_ALLOWED_DELAY, policy.min_delay)
        max_delay = max(min_delay, policy.max_delay)
        return random.uniform(min_delay, max_delay)
