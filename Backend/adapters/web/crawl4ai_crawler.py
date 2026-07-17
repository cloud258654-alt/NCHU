"""
Crawl4AI async web crawler adapter for generic non-PTT URLs.

Uses the `crawl4ai` library's AsyncWebCrawler to fetch and parse
general web pages into BI-RMP crawl_posts payloads.

This adapter targets URLs that do NOT belong to ptt / google_maps / threads.
It is registered as platform=`web` and outputs through the standard
supabase persistence layer (db.save_crawled_posts).

Usage:
    import asyncio
    from adapters.web.crawl4ai_crawler import crawl_urls_with_crawl4ai

    posts = asyncio.run(crawl_urls_with_crawl4ai(
        ["https://example.com/article"],
        keyword="test",
    ))
"""

from __future__ import annotations

import asyncio
import logging
import time

from adapters.web.crawl4ai_models import Crawl4AIDiagnostics, Crawl4AIResult
from adapters.web.crawl4ai_utils import result_to_post_payload

logger = logging.getLogger("adapters.web")


async def crawl_urls_with_crawl4ai(
    urls: list[str],
    *,
    keyword: str | None = None,
    crawl_job_id: str | None = None,
    service_task_id: str | None = None,
    max_concurrency: int = 5,
    timeout_seconds: int = 30,
) -> list[dict]:
    """Crawl multiple URLs using Crawl4AI AsyncWebCrawler.

    Each URL is fetched independently; failure of one does not affect others.
    Results are returned as BI-RMP crawl_posts payload dicts.

    Args:
        urls: List of URLs to crawl.
        keyword: Optional keyword for context.
        crawl_job_id: Optional crawl job identifier.
        service_task_id: Optional service task identifier.
        max_concurrency: Maximum concurrent crawls.
        timeout_seconds: Per-URL timeout in seconds.

    Returns:
        List of crawl_posts payload dicts (successful results only).
    """
    if not urls:
        return []

    diagnostics = Crawl4AIDiagnostics(urls_total=len(urls))
    started = time.time()

    _semaphore = asyncio.Semaphore(max_concurrency)

    async def _crawl_one(url: str) -> Crawl4AIResult | None:
        async with _semaphore:
            try:
                result = await _crawl_single(url, timeout_seconds=timeout_seconds)
            except Exception as exc:
                diagnostics.failed_count += 1
                diagnostics.errors.append({
                    "url": url,
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                })
                return None
            if result.success:
                diagnostics.success_count += 1
            else:
                diagnostics.failed_count += 1
                diagnostics.errors.append({
                    "url": url,
                    "error_type": result.error_message or "unknown",
                    "error_message": result.error_message or "",
                })
            return result

    tasks = [_crawl_one(url) for url in urls]
    raw_results: list[Crawl4AIResult | None] = await asyncio.gather(*tasks)

    diagnostics.elapsed = round(time.time() - started, 3)

    posts: list[dict] = []
    for result in raw_results:
        if result is None or not result.success:
            continue
        payload = result_to_post_payload(
            result,
            keyword=keyword,
            crawl_job_id=crawl_job_id,
        )
        posts.append(payload)

    logger.info(
        "Crawl4AI batch complete: total=%s success=%s failed=%s elapsed=%.2fs",
        diagnostics.urls_total,
        diagnostics.success_count,
        diagnostics.failed_count,
        diagnostics.elapsed,
    )

    return posts


async def _crawl_single(
    url: str,
    *,
    timeout_seconds: int = 30,
) -> Crawl4AIResult:
    """Crawl a single URL with Crawl4AI arun()."""

    started = time.monotonic()
    try:
        from crawl4ai import AsyncWebCrawler
    except ModuleNotFoundError:
        logger.error("crawl4ai package not installed. Install: pip install crawl4ai")
        return Crawl4AIResult(
            url=url,
            success=False,
            error_message="crawl4ai_not_installed",
        )

    try:
        kwargs: dict = {"timeout": timeout_seconds * 1000}
        try:
            from crawl4ai import CrawlerRunConfig, DefaultMarkdownGenerator
            kwargs["config"] = CrawlerRunConfig(
                markdown_generator=DefaultMarkdownGenerator(),
            )
        except ImportError:
            pass

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url, **kwargs)

        elapsed = (time.monotonic() - started) * 1000
        if result.success:
            return Crawl4AIResult(
                url=url,
                success=True,
                markdown=result.markdown or "",
                cleaned_html=getattr(result, "cleaned_html", "") or "",
                html=getattr(result, "html", "") or "",
                title=getattr(result, "metadata", {}).get("title", "")
                if isinstance(getattr(result, "metadata", None), dict)
                else "",
                metadata=result.metadata if isinstance(getattr(result, "metadata", None), dict) else {},
                elapsed_ms=elapsed,
            )
        else:
            return Crawl4AIResult(
                url=url,
                success=False,
                error_message=result.error_message or "crawl4ai_error",
                elapsed_ms=elapsed,
            )
    except Exception as exc:
        elapsed = (time.monotonic() - started) * 1000
        logger.debug("Crawl4AI fetch failed: url=%s error=%s", url, exc)
        return Crawl4AIResult(
            url=url,
            success=False,
            error_message=str(exc),
            elapsed_ms=elapsed,
        )


async def run_web_crawler(
    urls: list[str],
    *,
    keyword: str | None = None,
    crawl_job_id: str | None = None,
    service_task_id: str | None = None,
    max_concurrency: int = 5,
    timeout_seconds: int = 30,
    save_to_db: bool = False,
) -> dict:
    """Run the web Crawl4AI adapter and return a summary dict.

    When save_to_db=True, successful posts are persisted through
    db.save_crawled_post_records().
    """

    posts = await crawl_urls_with_crawl4ai(
        urls,
        keyword=keyword,
        crawl_job_id=crawl_job_id,
        service_task_id=service_task_id,
        max_concurrency=max_concurrency,
        timeout_seconds=timeout_seconds,
    )

    inserted = 0
    if save_to_db and posts:
        import core.supabase as db
        try:
            inserted = db.save_crawled_post_records(posts)
        except Exception as exc:
            logger.warning("Crawl4AI database write failed: %s", exc)

    return {
        "platform": "web",
        "status": "success" if posts else "empty_result",
        "inserted": inserted,
        "cards_found": len(posts),
        "elapsed": 0.0,
        "error_type": None,
        "error_message": None,
        "buffer_path": None,
        "diagnostics": {},
    }


from adapters.base import CommandModuleCrawler
from adapters.registry import CrawlerRegistry


class WebCrawler(CommandModuleCrawler):
    def __init__(self) -> None:
        super().__init__("web", "adapters.web.crawl4ai_crawler")


CrawlerRegistry.register("web", WebCrawler)
