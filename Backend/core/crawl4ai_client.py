"""
Async batch HTTP client for general URL fetching.

Provides a lightweight aiohttp-based fetcher as a shared utility.
For full Crawl4AI integration (JS rendering, markdown extraction),
use adapters.web.crawl4ai_crawler.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("core.crawl4ai")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_CONCURRENCY = 5
DEFAULT_TIMEOUT_SECONDS = 30


@dataclass(slots=True)
class FetchResult:
    url: str
    status: int | None = None
    html: str = ""
    error: str | None = None
    elapsed_ms: float = 0.0
    headers: dict[str, str] = field(default_factory=dict)


async def fetch_urls(
    urls: list[str],
    *,
    concurrency: int | None = None,
    timeout_seconds: float | None = None,
    user_agent: str | None = None,
    headers: dict[str, str] | None = None,
) -> list[FetchResult]:
    """Fetch multiple URLs concurrently using aiohttp with bounded concurrency."""
    if not urls:
        return []

    semaphore = asyncio.Semaphore(
        concurrency or _env_int("CRAWL4AI_CONCURRENCY", DEFAULT_CONCURRENCY)
    )
    timeout = timeout_seconds or _env_float("CRAWL4AI_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)
    ua = user_agent or os.getenv("CRAWL4AI_USER_AGENT", DEFAULT_USER_AGENT)

    async def _fetch_one(url: str) -> FetchResult:
        async with semaphore:
            return await _fetch(url, timeout=timeout, user_agent=ua, headers=headers)

    tasks = [_fetch_one(url) for url in urls]
    return list(await asyncio.gather(*tasks))


async def _fetch(
    url: str,
    *,
    timeout: float,
    user_agent: str,
    headers: dict[str, str] | None = None,
) -> FetchResult:
    import aiohttp
    started = time.monotonic()
    req_headers = {"User-Agent": user_agent, **(headers or {})}

    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.get(url, headers=req_headers) as response:
                html = await response.text(encoding="utf-8", errors="replace")
                return FetchResult(
                    url=url,
                    status=response.status,
                    html=html,
                    headers=dict(response.headers),
                    elapsed_ms=(time.monotonic() - started) * 1000,
                )
    except asyncio.TimeoutError:
        return FetchResult(url=url, error="timeout", elapsed_ms=(time.monotonic() - started) * 1000)
    except Exception as exc:
        return FetchResult(url=url, error=str(exc), elapsed_ms=(time.monotonic() - started) * 1000)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 1 else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= 0 else default
