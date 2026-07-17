from __future__ import annotations

from typing import Any


async def crawl4ai_page_snapshot(
    url: str,
    *,
    diagnostics: dict | None = None,
) -> dict[str, Any]:
    """Optional Crawl4AI fallback snapshot without remote extraction."""

    if diagnostics is not None:
        diagnostics["crawl4ai"]["attempted"] = True

    try:
        from crawl4ai import AsyncWebCrawler
    except ModuleNotFoundError:
        if diagnostics is not None:
            diagnostics["crawl4ai"]["error"] = "crawl4ai_not_installed"
        return {
            "success": False,
            "error": "crawl4ai_not_installed",
            "markdown": "",
            "metadata": {},
        }

    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)

        markdown = getattr(result, "markdown", "") or ""
        metadata = getattr(result, "metadata", {}) or {}
        success = bool(getattr(result, "success", False))

        if diagnostics is not None:
            diagnostics["crawl4ai"]["success"] = success
            diagnostics["crawl4ai"]["error"] = getattr(result, "error_message", None)

        return {
            "success": success,
            "error": getattr(result, "error_message", None),
            "markdown": markdown,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
    except Exception as exc:
        if diagnostics is not None:
            diagnostics["crawl4ai"]["error"] = str(exc)
        return {
            "success": False,
            "error": str(exc),
            "markdown": "",
            "metadata": {},
        }
