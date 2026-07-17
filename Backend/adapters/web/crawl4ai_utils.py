"""
Utility functions for converting Crawl4AI raw results into BI-RMP payloads.
"""

from __future__ import annotations

import hashlib
from typing import Any

from adapters.web.crawl4ai_models import Crawl4AIResult


def result_to_post_payload(
    result: Crawl4AIResult,
    *,
    keyword: str | None = None,
    crawl_job_id: str | None = None,
) -> dict[str, Any]:
    content = result.markdown or result.cleaned_html or result.html or ""

    source_url = result.url
    external_id = _stable_hash(source_url)

    raw_json: dict[str, Any] = {
        "platform": "web",
        "crawler": "crawl4ai",
        "success": result.success,
        "metadata": result.metadata,
        "error_message": result.error_message,
    }

    return {
        "source_url": source_url,
        "post_url": source_url,
        "external_id": external_id,
        "title": result.title or _title_from_url(source_url),
        "author_name": None,
        "author_id": None,
        "content": content,
        "post_time_raw": None,
        "post_time": None,
        "comments": [],
        "comment_count": 0,
        "reaction_count": 0,
        "source": "web",
        "keyword": keyword,
        "crawl_job_id": crawl_job_id,
        "platform": "web",
        "dedupe_key": f"web:crawl4ai:{external_id}",
        "raw_json": raw_json,
    }


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _title_from_url(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if path:
        return path.rsplit("/", 1)[-1] or path
    return parsed.netloc
