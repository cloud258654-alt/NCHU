from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchConfig:
    timeout_seconds: float = 20.0
    user_agent: str = "BI-RMP Source Discovery/1.0"
    searxng_base_url: str | None = None
    retry_attempts: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 8.0


def load_config(*, searxng_url: str | None = None) -> SearchConfig:
    return SearchConfig(
        timeout_seconds=float(os.getenv("SEARCH_TIMEOUT_SECONDS", "20")),
        user_agent=os.getenv("SEARCH_USER_AGENT", "BI-RMP Source Discovery/1.0"),
        searxng_base_url=searxng_url or os.getenv("SEARXNG_BASE_URL"),
        retry_attempts=int(os.getenv("SEARCH_RETRY_ATTEMPTS", "3")),
        retry_base_delay=float(os.getenv("SEARCH_RETRY_BASE_DELAY", "1.0")),
        retry_max_delay=float(os.getenv("SEARCH_RETRY_MAX_DELAY", "8.0")),
    )
