from __future__ import annotations

import asyncio

from core.analysis_pipeline import PostgresAnalysisQueue
from core.logger import get_logger


logger = get_logger("core.post_crawl_analysis")


async def enqueue_post_crawl_analysis(*, platform: str, keyword: str, crawl_job_id: str | None = None) -> None:
    """Queue canonical rows from one completed crawl job for offline analysis.

    This hook performs only the small database enqueue operation. The worker
    owns model execution, so crawler and webhook requests never wait for it.
    """

    if crawl_job_id is None:
        logger.warning("Analysis enqueue skipped because crawl_job_id is unavailable: platform=%s", platform)
        return
    try:
        queued = await asyncio.to_thread(PostgresAnalysisQueue().enqueue_crawl_job, crawl_job_id)
    except Exception as exc:
        logger.warning("Analysis enqueue failed for crawl job %s: %s", crawl_job_id, type(exc).__name__)
        return
    logger.info("Post-crawl analysis queued: platform=%s keyword=%s targets=%s", platform, keyword, queued)
