from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from core.logger import get_logger


logger = get_logger("core.crawl_scheduler")
BROWSER_PLATFORMS = frozenset({"google_maps", "threads"})
PlatformOperation = Callable[[], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class PlatformWork:
    platform: str
    operation: PlatformOperation


class CrawlScheduler:
    """Run platform pipelines concurrently with bounded browser resources."""

    def __init__(self, *, browser_concurrency: int = 2) -> None:
        if browser_concurrency <= 0:
            raise ValueError("browser_concurrency must be > 0")
        self.browser_concurrency = browser_concurrency
        self._browser_slots = asyncio.Semaphore(browser_concurrency)

    async def run_with_resources(
        self,
        platform: str,
        operation: PlatformOperation,
    ) -> dict[str, Any]:
        if platform not in BROWSER_PLATFORMS:
            return await operation()

        async with self._browser_slots:
            logger.info(
                "Browser slot acquired: platform=%s configured_slots=%s",
                platform,
                self.browser_concurrency,
            )
            return await operation()

    async def gather(self, work_items: Sequence[PlatformWork]) -> list[dict[str, Any]]:
        tasks = [
            asyncio.create_task(
                self._run_safely(work),
                name=f"crawl-platform:{work.platform}",
            )
            for work in work_items
        ]
        try:
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        results: list[dict[str, Any]] = []
        for work, raw_result in zip(work_items, raw_results, strict=True):
            if isinstance(raw_result, BaseException):
                results.append(_exception_result(work.platform, raw_result))
            else:
                results.append(raw_result)
        return results

    async def _run_safely(self, work: PlatformWork) -> dict[str, Any]:
        try:
            return await work.operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Uncaught platform pipeline failure: platform=%s", work.platform)
            return _exception_result(work.platform, exc)


def _exception_result(platform: str, exc: BaseException) -> dict[str, Any]:
    return {
        "platform": platform,
        "status": "failed",
        "inserted": 0,
        "cards_found": 0,
        "comments_found": 0,
        "elapsed": 0.0,
        "error_type": type(exc).__name__,
        "error_message": str(exc) or type(exc).__name__,
    }
