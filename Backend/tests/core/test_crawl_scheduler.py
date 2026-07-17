import asyncio

import pytest

from core.crawl_scheduler import CrawlScheduler, PlatformWork


@pytest.mark.asyncio
async def test_scheduler_isolates_platform_failures_and_preserves_result_order():
    scheduler = CrawlScheduler(browser_concurrency=2)
    completed = []

    async def success(platform, delay):
        await asyncio.sleep(delay)
        completed.append(platform)
        return {"platform": platform, "status": "success"}

    async def failure():
        await asyncio.sleep(0.01)
        raise RuntimeError("threads unavailable")

    results = await scheduler.gather(
        [
            PlatformWork("ptt", lambda: success("ptt", 0.03)),
            PlatformWork("google_maps", lambda: success("google_maps", 0.02)),
            PlatformWork("threads", failure),
        ]
    )

    assert [result["platform"] for result in results] == ["ptt", "google_maps", "threads"]
    assert [result["status"] for result in results] == ["success", "success", "failed"]
    assert results[2]["error_type"] == "RuntimeError"
    assert set(completed) == {"ptt", "google_maps"}


@pytest.mark.asyncio
async def test_scheduler_limits_only_browser_operations():
    scheduler = CrawlScheduler(browser_concurrency=1)
    browser_active = 0
    browser_max_active = 0
    ptt_started = asyncio.Event()

    async def browser_operation(platform):
        nonlocal browser_active, browser_max_active
        browser_active += 1
        browser_max_active = max(browser_max_active, browser_active)
        await asyncio.sleep(0.03)
        browser_active -= 1
        return {"platform": platform, "status": "success"}

    async def browser_pipeline(platform):
        return await scheduler.run_with_resources(
            platform,
            lambda: browser_operation(platform),
        )

    async def ptt_pipeline():
        ptt_started.set()
        await asyncio.sleep(0.01)
        return {"platform": "ptt", "status": "success"}

    results = await scheduler.gather(
        [
            PlatformWork("google_maps", lambda: browser_pipeline("google_maps")),
            PlatformWork("threads", lambda: browser_pipeline("threads")),
            PlatformWork("ptt", ptt_pipeline),
        ]
    )

    assert ptt_started.is_set()
    assert browser_max_active == 1
    assert all(result["status"] == "success" for result in results)
