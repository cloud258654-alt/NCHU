"""
Data models for Crawl4AI web crawler results.

All outputs are normalized to match BI-RMP crawl_posts payload conventions
before being passed through standardize_crawled_post().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Crawl4AIResult:
    url: str
    success: bool
    markdown: str = ""
    cleaned_html: str = ""
    html: str = ""
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    elapsed_ms: float = 0.0


@dataclass(slots=True)
class Crawl4AIDiagnostics:
    platform: str = "web"
    crawler: str = "crawl4ai"
    urls_total: int = 0
    success_count: int = 0
    failed_count: int = 0
    elapsed: float = 0.0
    errors: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "crawler": self.crawler,
            "urls_total": self.urls_total,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "elapsed": self.elapsed,
            "errors": list(self.errors),
        }
