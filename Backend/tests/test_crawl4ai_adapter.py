"""Tests for Crawl4AI web adapter.

All tests use mocks to avoid real network calls.
"""

import builtins
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from adapters.web.crawl4ai_crawler import (
    _crawl_single,
    crawl_urls_with_crawl4ai,
    run_web_crawler,
)
from adapters.web.crawl4ai_models import Crawl4AIDiagnostics, Crawl4AIResult
from adapters.web.crawl4ai_utils import result_to_post_payload


class TestCrawl4AIResultToPayload:
    """Verify Crawl4AI result → BI-RMP post payload conversion."""

    def test_result_to_post_payload_converts_successful_result(self):
        result = Crawl4AIResult(
            url="https://example.com/article/1",
            success=True,
            markdown="Article content here",
            title="Example Article",
            metadata={"description": "A test article"},
        )

        payload = result_to_post_payload(result, keyword="test")

        assert payload["source_url"] == "https://example.com/article/1"
        assert payload["post_url"] == "https://example.com/article/1"
        assert payload["title"] == "Example Article"
        assert payload["content"] == "Article content here"
        assert payload["source"] == "web"
        assert payload["platform"] == "web"
        assert payload["keyword"] == "test"
        assert payload["comment_count"] == 0
        assert payload["reaction_count"] == 0
        assert payload["comments"] == []
        assert payload["raw_json"]["platform"] == "web"
        assert payload["raw_json"]["crawler"] == "crawl4ai"
        assert payload["raw_json"]["success"] is True
        assert payload["raw_json"]["error_message"] is None

    def test_result_to_post_payload_falls_back_to_url_title(self):
        result = Crawl4AIResult(
            url="https://example.com/blog/post-42",
            success=True,
            markdown="Some content",
            title="",
        )

        payload = result_to_post_payload(result, keyword="test")

        assert payload["title"] == "post-42"

    def test_result_to_post_payload_uses_cleaned_html_fallback(self):
        result = Crawl4AIResult(
            url="https://example.com/page",
            success=True,
            markdown="",
            cleaned_html="<p>HTML content</p>",
        )

        payload = result_to_post_payload(result, keyword="test")

        assert payload["content"] == "<p>HTML content</p>"

    def test_result_to_post_payload_has_stable_external_id(self):
        result_a = Crawl4AIResult(
            url="https://example.com/same-url",
            success=True,
            markdown="content A",
        )
        result_b = Crawl4AIResult(
            url="https://example.com/same-url",
            success=True,
            markdown="content B",
        )

        id_a = result_to_post_payload(result_a)["external_id"]
        id_b = result_to_post_payload(result_b)["external_id"]

        assert id_a == id_b

    def test_result_to_post_payload_different_urls_have_different_ids(self):
        result_a = Crawl4AIResult(url="https://example.com/A", success=True)
        result_b = Crawl4AIResult(url="https://example.com/B", success=True)

        id_a = result_to_post_payload(result_a)["external_id"]
        id_b = result_to_post_payload(result_b)["external_id"]

        assert id_a != id_b


class TestCrawlURLsWithCrawl4AI:
    """Integration-style tests for crawl_urls_with_crawl4ai (mocked)."""

    @pytest.mark.asyncio
    async def test_empty_urls_returns_empty_list(self):
        posts = await crawl_urls_with_crawl4ai([], keyword="test")

        assert posts == []

    @pytest.mark.asyncio
    async def test_single_successful_url_returns_post(self, monkeypatch):
        fake_result = Crawl4AIResult(
            url="https://example.com/1",
            success=True,
            markdown="Content",
            title="Title",
        )

        async def fake_crawl(url, *, timeout_seconds=30):
            return fake_result

        monkeypatch.setattr(
            "adapters.web.crawl4ai_crawler._crawl_single",
            fake_crawl,
        )

        posts = await crawl_urls_with_crawl4ai(
            ["https://example.com/1"],
            keyword="test",
        )

        assert len(posts) == 1
        assert posts[0]["source_url"] == "https://example.com/1"
        assert posts[0]["content"] == "Content"

    @pytest.mark.asyncio
    async def test_failed_url_does_not_block_others(self, monkeypatch):
        async def fake_crawl(url, *, timeout_seconds=30):
            if "fail" in url:
                return Crawl4AIResult(
                    url=url,
                    success=False,
                    error_message="connection_error",
                )
            return Crawl4AIResult(
                url=url,
                success=True,
                markdown="Content",
                title="Title",
            )

        monkeypatch.setattr(
            "adapters.web.crawl4ai_crawler._crawl_single",
            fake_crawl,
        )

        posts = await crawl_urls_with_crawl4ai(
            [
                "https://example.com/good-1",
                "https://example.com/fail-1",
                "https://example.com/good-2",
            ],
            keyword="test",
        )

        assert len(posts) == 2
        urls = {p["source_url"] for p in posts}
        assert "https://example.com/good-1" in urls
        assert "https://example.com/good-2" in urls
        assert "https://example.com/fail-1" not in urls

    @pytest.mark.asyncio
    async def test_multiple_successful_urls_all_returned(self, monkeypatch):
        async def fake_crawl(url, *, timeout_seconds=30):
            return Crawl4AIResult(
                url=url,
                success=True,
                markdown=f"Content from {url}",
                title="Title",
            )

        monkeypatch.setattr(
            "adapters.web.crawl4ai_crawler._crawl_single",
            fake_crawl,
        )

        posts = await crawl_urls_with_crawl4ai(
            ["https://example.com/1", "https://example.com/2", "https://example.com/3"],
            keyword="test",
        )

        assert len(posts) == 3

    @pytest.mark.asyncio
    async def test_exception_in_crawl_single_is_handled(self, monkeypatch):
        async def fake_crawl(url, *, timeout_seconds=30):
            if "crash" in url:
                raise RuntimeError("Unexpected crash")
            return Crawl4AIResult(url=url, success=True, markdown="OK")

        monkeypatch.setattr(
            "adapters.web.crawl4ai_crawler._crawl_single",
            fake_crawl,
        )

        posts = await crawl_urls_with_crawl4ai(
            ["https://example.com/crash", "https://example.com/ok"],
            keyword="test",
        )

        assert len(posts) == 1
        assert posts[0]["source_url"] == "https://example.com/ok"


class TestCrawlSingle:
    """Unit tests for _crawl_single without real Crawl4AI."""

    @pytest.mark.asyncio
    async def test_crawl4ai_not_installed_returns_failure(self, monkeypatch):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "crawl4ai":
                raise ModuleNotFoundError("crawl4ai")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        result = await _crawl_single("https://example.com")
        assert not result.success
        assert result.error_message == "crawl4ai_not_installed"


class TestCrawl4AIDiagnostics:
    """Verify diagnostics tracking."""

    def test_diagnostics_defaults(self):
        diag = Crawl4AIDiagnostics()

        assert diag.platform == "web"
        assert diag.crawler == "crawl4ai"
        assert diag.urls_total == 0
        assert diag.success_count == 0
        assert diag.failed_count == 0
        assert diag.errors == []

    def test_diagnostics_as_dict(self):
        diag = Crawl4AIDiagnostics(urls_total=5, success_count=3, failed_count=2)
        diag.errors.append({"url": "https://x.com", "error_type": "timeout", "error_message": "timeout"})

        d = diag.as_dict()

        assert d["platform"] == "web"
        assert d["urls_total"] == 5
        assert d["success_count"] == 3
        assert d["failed_count"] == 2
        assert len(d["errors"]) == 1


class TestWebCrawlerNotReplaceExisting:
    """Verify the web adapter does NOT replace existing platforms."""

    def test_registry_contains_all_platforms(self):
        from adapters.registry import CrawlerRegistry, load_builtin_crawlers

        load_builtin_crawlers()
        platforms = set(CrawlerRegistry.available())

        assert "ptt" in platforms
        assert "google_maps" in platforms
        assert "threads" in platforms
        assert "web" in platforms
        assert len(platforms) >= 4

    def test_no_new_db_tables_in_schema(self):
        import re
        schema_path = __import__("pathlib").Path(__file__).resolve().parents[1] / "database" / "schema.sql"
        if not schema_path.exists():
            schema_path = __import__("pathlib").Path(__file__).resolve().parents[2] / "database" / "schema.sql"

        sql = schema_path.read_text(encoding="utf-8")

        forbidden_tables = [
            "CREATE TABLE google_maps_posts",
            "CREATE TABLE threads_posts",
            "CREATE TABLE web_pages",
            "CREATE TABLE crawl4ai",
        ]
        for table in forbidden_tables:
            assert table not in sql, f"Forbidden table found: {table}"


class TestRunWebCrawler:
    """Verify run_web_crawler summary output shape."""

    @pytest.mark.asyncio
    async def test_run_web_crawler_returns_summary_dict(self, monkeypatch):
        async def fake_crawl_urls(*args, **kwargs):
            return []

        monkeypatch.setattr(
            "adapters.web.crawl4ai_crawler.crawl_urls_with_crawl4ai",
            fake_crawl_urls,
        )

        result = await run_web_crawler(
            ["https://example.com/1"],
            keyword="test",
            save_to_db=False,
        )

        assert result["platform"] == "web"
        assert result["status"] in ("success", "empty_result")
        assert "inserted" in result
        assert "cards_found" in result
        assert "buffer_path" in result
