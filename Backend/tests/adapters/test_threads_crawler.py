import pytest
import re
import json
from pathlib import Path
from datetime import datetime, timezone
from argparse import Namespace
from types import SimpleNamespace

# Import helper functions from crawler.py
from adapters.threads import crawler as threads_crawler
from adapters.threads.crawler import parse_counts
from core.search_models import SearchResult


@pytest.mark.asyncio
async def test_scrape_threads_stops_before_browser_when_discovery_uses_soft_budget(monkeypatch):
    ticks = iter([100.0, 101.0])

    async def fake_discover(*args, **kwargs):
        return []

    monkeypatch.setattr(
        threads_crawler,
        "time",
        SimpleNamespace(monotonic=lambda: next(ticks)),
    )
    monkeypatch.setattr(threads_crawler, "discover_threads_urls", fake_discover)
    args = Namespace(business_name="Example Shop", input_keyword=None)

    posts = await threads_crawler.scrape_threads(
        "Example Shop",
        max_scroll=1,
        max_minutes=0.01,
        headless=True,
        args=args,
    )

    assert posts == []
    assert args.threads_deadline_reached is True

def test_parse_counts():
    # 1. 12 likes
    assert parse_counts("12 likes") == (12, 0, 0)
    # 2. 1.2K likes
    assert parse_counts("1.2K likes") == (1200, 0, 0)
    # 3. 3 replies
    assert parse_counts("3 replies") == (0, 3, 0)
    # 4. 4 reposts
    assert parse_counts("4 reposts") == (0, 0, 4)
    # 5. Combined text
    assert parse_counts("1.5M likes\n200 replies\n15 reposts") == (1500000, 200, 15)
    # 6. Chinese text / mixed
    assert parse_counts("12 個讚 3 則回覆") == (12, 3, 0)
    assert parse_counts("324 轉發") == (0, 0, 324)

def test_url_standardization():
    from adapters.threads.crawler import standardize_threads_url_info
    # Test normalization of URL, username, and post_id extraction
    url1 = "https://www.threads.net/@user.name/post/C9S2t-xyZaB?xmt=AQG"
    norm_url, username, post_id = standardize_threads_url_info(url1)
    assert norm_url == "https://www.threads.net/@user.name/post/C9S2t-xyZaB/"
    assert username == "user.name"
    assert post_id == "C9S2t-xyZaB"

    # Test direct URL without query parameters
    url2 = "https://www.threads.net/@another_user/post/C_xyz123"
    norm_url2, username2, post_id2 = standardize_threads_url_info(url2)
    assert norm_url2 == "https://www.threads.net/@another_user/post/C_xyz123/"
    assert username2 == "another_user"
    assert post_id2 == "C_xyz123"

def test_content_cleaning():
    from adapters.threads.crawler import clean_threads_content
    # Test cleaning UI noise, "翻譯", "See translation", date patterns, etc.
    content = "這是真實內容\n翻譯\nSee translation\n2026-07-05\n12\n1.2K"
    cleaned = clean_threads_content(content)
    assert cleaned == "這是真實內容"

    content2 = "See translation\n\n123"
    cleaned2 = clean_threads_content(content2)
    assert cleaned2 == ""

def test_payload_validation():
    from adapters.threads.crawler import validate_post_payload
    # Valid post
    valid_post = {
        "post_url": "https://www.threads.net/@user/post/123/",
        "content": "Hello world",
        "author_id": "user",
        "author_name": "user_display",
    }
    assert validate_post_payload(valid_post) is True

    # Missing URL
    invalid_post1 = {
        "post_url": "",
        "content": "Hello world",
        "author_id": "user",
        "author_name": "user_display",
    }
    assert validate_post_payload(invalid_post1) is False

    # Missing content
    invalid_post2 = {
        "post_url": "https://www.threads.net/@user/post/123/",
        "content": "",
        "author_id": "user",
        "author_name": "user_display",
    }
    assert validate_post_payload(invalid_post2) is False

    # Missing author info (username/author_id/author_name)
    invalid_post3 = {
        "post_url": "https://www.threads.net/@user/post/123/",
        "content": "Hello world",
        "author_id": "",
        "author_name": "",
    }
    assert validate_post_payload(invalid_post3) is False


def test_threads_relevance_requires_business_identity_not_full_query_phrase():
    assert threads_crawler._matches_threads_business(
        "Example Shop has a new menu",
        "Example Shop",
    )
    assert not threads_crawler._matches_threads_business(
        "Generic store features post",
        "Example Shop",
    )


def test_threads_discovery_falls_back_from_intent_to_business_name():
    args = Namespace(business_name="Example Shop", input_keyword="store features")

    assert threads_crawler._threads_search_queries("Example Shop store features", args) == [
        "Example Shop store features",
        "Example Shop",
    ]


def test_threads_discovery_ignores_parallel_context_from_adapter_environment(monkeypatch):
    monkeypatch.setenv("BI_RMP_INPUT_KEYWORD", "store features")
    args = Namespace(business_name="Example Shop", input_keyword=None)

    assert threads_crawler._threads_search_queries("Example Shop store features", args) == ["Example Shop"]


def test_threads_body_classification_detects_block_conditions():
    detected = threads_crawler._classify_threads_body(
        "Please log in. CAPTCHA verification required. This content is restricted.",
        "https://www.threads.net/login",
    )

    assert detected["login_wall_detected"] is True
    assert detected["captcha_detected"] is True
    assert detected["restricted_detected"] is True


@pytest.mark.asyncio
async def test_discover_threads_urls_searches_current_and_legacy_domains(monkeypatch):
    captured_queries = []

    class FakeEngine:
        async def search(self, query):
            captured_queries.append(query.rendered_query)
            return []

    monkeypatch.setattr(threads_crawler, "create_engine", lambda name, config: FakeEngine())

    await threads_crawler.discover_threads_urls(
        "Example",
        Namespace(engine="duckduckgo", searxng_url=None),
        max_results=10,
    )

    assert 'site:threads.com/@/post "Example"' in captured_queries
    assert '"Example" site:threads.com' in captured_queries
    assert 'site:threads.net/@/post "Example"' in captured_queries
    assert '"Example" site:threads.net' in captured_queries


@pytest.mark.asyncio
async def test_discover_threads_urls_accepts_threads_com(monkeypatch):
    class FakeEngine:
        async def search(self, query):
            return [
                SearchResult(
                    engine="duckduckgo",
                    query=query.rendered_query,
                    url="https://www.threads.com/@brand/post/abc123?x=1",
                    title="Brand",
                    rank=1,
                )
            ]

    monkeypatch.setattr(threads_crawler, "create_engine", lambda name, config: FakeEngine())

    urls = await threads_crawler.discover_threads_urls(
        "Example",
        Namespace(engine="duckduckgo", searxng_url=None),
        max_results=10,
    )

    assert urls == ["https://www.threads.com/@brand/post/abc123/"]


def test_threads_context_uses_storage_state_when_present(monkeypatch, tmp_path):
    state_path = tmp_path / "threads_state.json"
    state_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(threads_crawler.runtime_settings, "THREADS_STORAGE_STATE_PATH", str(state_path))

    options = threads_crawler._threads_context_options()

    assert options["storage_state"] == str(state_path)


@pytest.mark.asyncio
async def test_threads_wait_requires_post_link_and_reports_login_wall(monkeypatch):
    class FakePage:
        async def wait_for_selector(self, selector, timeout=None):
            assert selector == threads_crawler.POST_LINK_SELECTOR
            raise TimeoutError("no post links")

    diagnostics = threads_crawler._new_threads_page_diagnostics()
    diagnostics["login_wall_detected"] = True
    monkeypatch.setattr(
        threads_crawler,
        "_collect_threads_page_diagnostics",
        lambda page: _async_value(diagnostics),
    )
    monkeypatch.setattr(
        threads_crawler,
        "_capture_threads_debug_artifacts",
        lambda page, args, **kwargs: _async_value(diagnostics),
    )

    with pytest.raises(RuntimeError, match="login/session blocked"):
        await threads_crawler._wait_for_threads_search_results(FakePage(), Namespace(crawl_job_id="1"))


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_threads_debug_artifacts_are_written(monkeypatch, tmp_path):
    class FakeLocator:
        def __init__(self, text="", count=0):
            self.text = text
            self._count = count

        async def inner_text(self, timeout=None):
            return self.text

        async def count(self):
            return self._count

    class FakePage:
        url = "https://www.threads.net/login"

        async def title(self):
            return "Threads"

        def locator(self, selector):
            if selector == "body":
                return FakeLocator("Please log in. CAPTCHA verification required.", 0)
            return FakeLocator("", 0)

        async def screenshot(self, path, full_page=True):
            Path(path).write_bytes(b"png")

        async def content(self):
            return "<html><body>Please log in</body></html>"

    monkeypatch.setattr(threads_crawler, "THREADS_DEBUG_ROOT", tmp_path / "debug" / "threads")
    args = Namespace(crawl_job_id="job-1")

    diagnostics = await threads_crawler._capture_threads_debug_artifacts(
        FakePage(),
        args,
        reason="blocked",
    )

    artifact_dir = tmp_path / "debug" / "threads" / "job-1"
    assert (artifact_dir / "screenshot.png").exists()
    assert (artifact_dir / "page.html").exists()
    payload = json.loads((artifact_dir / "diagnostics.json").read_text(encoding="utf-8"))
    assert payload["login_wall_detected"] is True
    assert payload["captcha_detected"] is True
    assert diagnostics["debug_artifacts"]["directory"] == str(artifact_dir)


@pytest.mark.asyncio
async def test_scrape_threads_runs_all_query_attempts(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    visited_urls = []

    # Mock Playwright Page
    mock_page = MagicMock()
    mock_page.url = "https://www.threads.com/search"

    async def mock_goto(url, wait_until=None, timeout=None):
        visited_urls.append(url)
        mock_page.url = url

    mock_page.goto = mock_goto
    mock_page.evaluate = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.add_init_script = AsyncMock()
    mock_page.close = AsyncMock()

    # Mock Playwright Context
    mock_context = MagicMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    # Mock Playwright Browser
    mock_browser = MagicMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    # Mock Playwright chromium and context manager
    mock_playwright = MagicMock()
    mock_playwright.chromium = MagicMock()
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    class MockPlaywrightContext:
        async def __aenter__(self):
            return mock_playwright
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    # Mock discover_threads_urls to return empty (so it uses search fallback)
    monkeypatch.setattr(threads_crawler, "discover_threads_urls", lambda *args, **kwargs: _async_value([]))
    
    # Mock playwright async_playwright
    monkeypatch.setattr("playwright.async_api.async_playwright", MockPlaywrightContext)

    # Mock search results wait to succeed
    monkeypatch.setattr(threads_crawler, "_wait_for_threads_search_results", lambda page, args, timeout=None: _async_value(True))
    
    # Mock bypass_login_wall to do nothing
    monkeypatch.setattr(threads_crawler, "bypass_login_wall", lambda page: _async_value(None))

    # Mock parse_visible_cards_helper to add different posts based on URL query
    async def fake_parse_visible_cards(page, all_parsed_posts_map, keyword, args, crawl_started_at):
        if "store%20features" in page.url:
            all_parsed_posts_map["https://www.threads.net/@user1/post/p1/"] = {
                "post_url": "https://www.threads.net/@user1/post/p1/",
                "content": "Example Shop is great with store features",
                "author_id": "user1",
                "author_name": "User One",
                "raw_json": {"comments": []}
            }
        else:
            all_parsed_posts_map["https://www.threads.net/@user2/post/p2/"] = {
                "post_url": "https://www.threads.net/@user2/post/p2/",
                "content": "Example Shop has good food",
                "author_id": "user2",
                "author_name": "User Two",
                "raw_json": {"comments": []}
            }

    monkeypatch.setattr(threads_crawler, "parse_visible_cards_helper", fake_parse_visible_cards)

    args = Namespace(
        business_name="Example Shop",
        input_keyword="store features",
        headless=True,
        max_scroll=1,
        max_minutes=1.0,
        max_results=10,
        platform_max_results=10,
        threads_max_posts=10,
        platform_max_scroll=1,
        threads_max_scroll=1,
        fetch_comments=False,
    )

    results = await threads_crawler.scrape_threads(
        keyword="Example Shop store features",
        max_scroll=1,
        max_minutes=1.0,
        headless=True,
        args=args,
    )

    # Assert both queries were executed in order: specific then broad
    assert "https://www.threads.com/search?q=Example%20Shop%20store%20features" in visited_urls
    assert "https://www.threads.com/search?q=Example%20Shop" in visited_urls

    # Assert results from both queries were merged
    post_urls = {post["post_url"] for post in results}
    assert "https://www.threads.net/@user1/post/p1/" in post_urls
    assert "https://www.threads.net/@user2/post/p2/" in post_urls
