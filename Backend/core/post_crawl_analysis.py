from __future__ import annotations

from core.logger import get_logger


logger = get_logger("core.post_crawl_analysis")


async def enqueue_post_crawl_analysis(*, platform: str, keyword: str) -> None:
    """Post-crawl analysis hook.

    The current MVP records the hook without running an LLM job. Actual
    sentiment/topic/risk processing should write to analysis_results later.
    """

    logger.info("Post-crawl analysis queued: platform=%s keyword=%s", platform, keyword)
