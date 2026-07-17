import asyncio
from argparse import Namespace
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError

import pytest

from adapters.base import CommandModuleCrawler
import sys

from adapters.ptt import crawler as ptt_crawler
from adapters.ptt.crawler import (
    PTT_ERROR_TYPES,
    _article_matches_business,
    _fetch_error_type,
    _query_variants,
    _query_matches_content,
    normalize_ptt_article_url,
    parse_ptt_article_html,
    scrape_ptt,
)
from adapters.ptt.parser import parse_ptt_index_html
from core.supabase import PersistenceResult, PersistenceStageResult
from core.anti_block import PlatformPolicy


@pytest.mark.asyncio
async def test_scrape_ptt_stops_after_discovery_when_soft_deadline_is_reached(monkeypatch):
    async def fake_discover(*args, **kwargs):
        return ["https://www.ptt.cc/bbs/Food/M.1234567890.A.123.html"]

    monkeypatch.setattr(ptt_crawler, "discover_ptt_urls", fake_discover)
    args = Namespace(business_name="Demo Shop", input_keyword=None)

    posts = await scrape_ptt(
        "Demo Shop",
        max_results=10,
        args=args,
        deadline=ptt_crawler.time.monotonic() - 1,
    )

    assert posts == []
    assert args.ptt_deadline_reached is True


PTT_HTML = """
<html>
<body>
<div id="main-content" class="bbs-screen bbs-content">
<div class="article-metaline"><span class="article-meta-tag">作者</span><span class="article-meta-value">alice (Alice)</span></div>
<div class="article-metaline"><span class="article-meta-tag">看板</span><span class="article-meta-value">Food</span></div>
<div class="article-metaline"><span class="article-meta-tag">標題</span><span class="article-meta-value">[食記] Demo Shop 牛肉湯</span></div>
<div class="article-metaline"><span class="article-meta-tag">時間</span><span class="article-meta-value">Sat Jul  4 12:34:56 2026</span></div>
Demo Shop 的牛肉湯正文。
<div class="push"><span class="f1 hl push-tag">推 </span><span class="f3 hl push-userid">bob</span><span class="f3 push-content">: 好吃</span><span class="push-ipdatetime"> 07/04 13:00</span></div>
<div class="push"><span class="f1 hl push-tag">噓 </span><span class="f3 hl push-userid">carol</span><span class="f3 push-content">: 太鹹</span><span class="push-ipdatetime"> 07/04 13:05</span></div>
<div class="push"><span class="hl push-tag">→ </span><span class="f3 hl push-userid">dave</span><span class="f3 push-content">: 排隊很久</span><span class="push-ipdatetime"> 07/04 13:10</span></div>
<span class="f2">※ 發信站: 批踢踢實業坊(ptt.cc)</span>
</div>
</body>
</html>
"""


def _fake_ptt_post() -> dict:
    return {
        "source_url": "https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html",
        "post_url": "https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html",
        "external_id": "M.1788888888.A.ABC.html",
        "board": "Food",
        "author_name": "Alice",
        "author_id": "alice",
        "title": "Demo Shop",
        "content": "Demo Shop beef soup",
        "post_time_raw": "Fri Jul 10 10:00:00 2026",
        "post_time": datetime.now(timezone.utc),
        "comments": [],
        "comment_count": 0,
        "reaction_count": 0,
        "raw_json": {"platform": "ptt", "comments": []},
    }


def test_parse_ptt_article_html_extracts_article_fields_comments_and_metrics():
    post = parse_ptt_article_html(
        PTT_HTML,
        url="https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html",
    )

    assert post["source_url"] == "https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html"
    assert post["external_id"] == "M.1788888888.A.ABC.html"
    assert post["board"] == "Food"
    assert post["author_id"] == "alice"
    assert post["author_name"] == "Alice"
    assert post["title"] == "[食記] Demo Shop 牛肉湯"
    assert "Demo Shop 的牛肉湯正文" in post["content"]
    assert post["comment_count"] == 3
    assert post["like_count"] == 1
    assert post["push_count"] == 1
    assert post["boo_count"] == 1
    assert post["arrow_count"] == 1
    assert post["ptt_net_score"] == 0
    assert post["normalized_score"] == pytest.approx(0.5)
    assert post["ptt_metrics"]["push_count"] == 1
    assert [comment["comment_type"] for comment in post["comments"]] == ["push", "boo", "arrow"]
    assert post["raw_json"]["ptt_metrics"]["comment_count"] == 3


def test_parse_ptt_index_html_parses_normal_ptt_index_row():
    html = """
    <div class="r-ent">
      <div class="title">
        <a href="/bbs/Food/M.1234567890.A.html">[食記] 台南牛肉湯</a>
      </div>
      <div class="meta">
        <div class="author">cloud</div>
        <div class="date">7/08</div>
      </div>
    </div>
    """

    assert parse_ptt_index_html(html) == [
        {
            "title": "[食記] 台南牛肉湯",
            "author_name": "cloud",
            "post_time_raw": "7/08",
            "post_url": "https://www.ptt.cc/bbs/Food/M.1234567890.A.html",
        }
    ]


def test_parse_ptt_index_html_skips_deleted_rows_without_title_link():
    html = """
    <div class="r-ent">
      <div class="title">
        (本文已被刪除) [cloud]
      </div>
      <div class="meta">
        <div class="author">-</div>
        <div class="date">7/08</div>
      </div>
    </div>
    """

    assert parse_ptt_index_html(html) == []


def test_normalize_ptt_article_url_accepts_only_article_urls():
    assert (
        normalize_ptt_article_url("https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html?x=1")
        == "https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html"
    )
    assert normalize_ptt_article_url("https://www.ptt.cc/bbs/Food/index.html") is None
    assert normalize_ptt_article_url("https://www.ptt.cc/bbs/Food/search?q=Demo") is None
    assert normalize_ptt_article_url("https://example.com/bbs/Food/M.1788888888.A.ABC.html") is None


def test_query_matches_content_uses_terms_for_business_plus_keyword():
    assert _query_matches_content("Demo Shop beef soup", "Demo Shop has a beef soup article")
    assert not _query_matches_content("Demo Shop noodles", "Demo Shop has a beef soup article")


def test_ptt_query_variants_never_search_generic_keyword_alone():
    variants = _query_variants(
        "Example Shop store features",
        business_name="Example Shop",
        keyword="store features",
    )

    assert "store features" not in variants
    assert variants == ["Example Shop store features", "Example Shop"]


def test_ptt_query_variants_do_not_duplicate_business_as_keyword():
    assert _query_variants(
        "Example Shop",
        business_name="Example Shop",
        keyword="Example Shop",
    ) == ["Example Shop"]


def test_ptt_article_must_contain_business_identity():
    assert _article_matches_business(
        {"title": "Example Shop review", "content": "great service"},
        "Example Shop",
    )
    assert not _article_matches_business(
        {"title": "Store features", "content": "another restaurant"},
        "Example Shop",
    )


def test_ptt_supported_error_types_and_http_mapping():
    assert PTT_ERROR_TYPES == {
        "timeout",
        "connection_reset",
        "http_403",
        "http_404",
        "http_429",
        "fetch_failed",
        "parse_failed",
        "empty_result",
        "fetch_zero_yield",
        "parser_zero_yield",
        "buffer_write_failed",
        "db_write_failed",
        "persistence_partial_failure",
        "unknown",
    }
    assert _fetch_error_type(TimeoutError("timed out")) == "timeout"
    assert _fetch_error_type(ConnectionResetError("reset")) == "connection_reset"
    assert _fetch_error_type(HTTPError("https://www.ptt.cc", 403, "Forbidden", {}, BytesIO())) == "http_403"
    assert _fetch_error_type(HTTPError("https://www.ptt.cc", 404, "Not Found", {}, BytesIO())) == "http_404"
    assert _fetch_error_type(HTTPError("https://www.ptt.cc", 429, "Too Many Requests", {}, BytesIO())) == "http_429"


def test_ptt_diagnostic_alias_fields_are_synced():
    diagnostics = {
        "discovery": {"urls_discovered": 3, "urls_after_dedupe": 2},
        "fetch": {"success": 1, "failed": 1},
        "parse": {"success": 1},
        "filter": {"kept_posts": 1, "dropped_by_relevance": 1, "date_rejected": 2},
    }

    ptt_crawler._sync_ptt_diagnostic_aliases(diagnostics)

    assert diagnostics["discovery"]["article_urls_discovered"] == 3
    assert diagnostics["discovery"]["article_urls_validated"] == 2
    assert diagnostics["fetch"]["article_fetch_success"] == 1
    assert diagnostics["fetch"]["article_fetch_failed"] == 1
    assert diagnostics["parse"]["articles_parsed"] == 1
    assert diagnostics["filter"]["keyword_matched"] == 1
    assert diagnostics["filter"]["keyword_rejected"] == 1
    assert diagnostics["filter"]["date_rejected"] == 2


def test_ptt_empty_result_after_filters_is_success_not_failure():
    diagnostics = {
        "discovery": {"urls_after_dedupe": 3},
        "fetch": {"attempted": 3, "success": 3, "last_error_message": None},
        "parse": {"failed": 0},
        "rolling_delta": {"items_scanned": 0, "delta_items": 0},
        "error": {"type": None, "message": None, "recoverable": None},
    }

    status = ptt_crawler._ptt_status([], buffer_ok=True, db_error=None, diagnostics=diagnostics)
    outcome = ptt_crawler._ptt_outcome(
        status=status,
        diagnostics=diagnostics,
        canonical_posts_written=0,
        canonical_comments_written=0,
    )

    assert status == "success"
    assert outcome == "success_no_results"
    assert diagnostics["error"]["type"] is None


def test_ptt_fetch_zero_yield_remains_failure():
    diagnostics = {
        "discovery": {"urls_after_dedupe": 2},
        "fetch": {"attempted": 2, "success": 0, "last_error_message": "connection reset"},
        "parse": {"failed": 0},
        "rolling_delta": {"items_scanned": 0, "delta_items": 0},
        "error": {"type": None, "message": None, "recoverable": None},
    }

    status = ptt_crawler._ptt_status([], buffer_ok=True, db_error=None, diagnostics=diagnostics)

    assert status == "failed"
    assert diagnostics["error"]["type"] == "fetch_zero_yield"
    assert diagnostics["error"]["message"] == "connection reset"


@pytest.mark.asyncio
async def test_scrape_ptt_does_not_require_board(monkeypatch):
    async def fake_discover(query, max_results, args):
        assert query == "Demo Shop"
        assert max_results == 1
        assert args.board is None
        return ["https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html"]

    monkeypatch.setattr("adapters.ptt.crawler.discover_ptt_urls", fake_discover)
    async def fake_fetch_article(session, url, **kwargs):
        return parse_ptt_article_html(PTT_HTML, url=url)

    monkeypatch.setattr("adapters.ptt.crawler._fetch_article_async", fake_fetch_article)
    args = Namespace(
        board=None,
        date_range="all",
        since_days=None,
        start_date=None,
        end_date=None,
        keep_unknown_time=False,
    )

    posts = await scrape_ptt("Demo Shop", max_results=1, args=args)

    assert len(posts) == 1
    assert posts[0]["board"] == "Food"


@pytest.mark.asyncio
async def test_scrape_ptt_never_fetches_more_than_two_articles_concurrently(monkeypatch):
    active = 0
    peak = 0
    urls = [f"https://www.ptt.cc/bbs/Food/M.178888888{i}.A.ABC.html" for i in range(5)]

    async def fake_discover(*args, **kwargs):
        return urls

    async def fake_fetch(session, url, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return parse_ptt_article_html(PTT_HTML, url=url)

    policy = ptt_crawler.CrawlPolicy(
        {"ptt": PlatformPolicy(min_delay=0, max_delay=0, max_concurrency=5)}
    )
    async def no_wait(self, platform, action="request"):
        return 0.0

    monkeypatch.setattr(ptt_crawler.CrawlPolicy, "load", lambda: policy)
    monkeypatch.setattr(ptt_crawler.RateLimiter, "acquire", no_wait)
    monkeypatch.setattr(ptt_crawler, "discover_ptt_urls", fake_discover)
    monkeypatch.setattr(ptt_crawler, "_fetch_article_async", fake_fetch)
    args = Namespace(
        board=None,
        business_name=None,
        input_keyword=None,
        date_range="all",
        since_days=None,
        start_date=None,
        end_date=None,
        keep_unknown_time=True,
    )

    await scrape_ptt("Demo Shop", max_results=5, args=args)

    assert peak == 2


def test_fetch_article_preserves_ptt_over18_cookie(monkeypatch):
    captured = {}

    def fake_fetch(url, *, headers, timeout, diagnostics):
        captured["headers"] = headers
        return PTT_HTML

    monkeypatch.setattr("adapters.ptt.cache.get_cached_article", lambda url, diagnostics=None: None)
    monkeypatch.setattr("adapters.ptt.cache.set_cached_article", lambda url, payload, diagnostics=None: True)
    monkeypatch.setattr("adapters.ptt.cache.is_quarantined", lambda url, diagnostics=None: False)
    monkeypatch.setattr("adapters.ptt.crawler._fetch_text_with_retry", fake_fetch)

    post = ptt_crawler._fetch_article("https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html")

    assert post["source_url"] == "https://www.ptt.cc/bbs/Food/M.1788888888.A.ABC.html"
    assert captured["headers"] == {"Cookie": "over18=1"}


@pytest.mark.asyncio
async def test_ptt_main_writes_buffer_before_db_in_service_mode(monkeypatch, tmp_path):
    calls = []

    async def fake_scrape(query, *, max_results, args, diagnostics=None):
        return [_fake_ptt_post()]

    def fake_buffer(posts, *, query, crawl_job_id=None, service_task_id=None):
        calls.append("buffer")
        path = tmp_path / "buffer.jsonl"
        path.write_text("{}", encoding="utf-8")
        return path

    def fake_save(posts):
        calls.append("db")
        return PersistenceResult([PersistenceStageResult("canonical_posts", True, len(posts), len(posts))])

    monkeypatch.setattr(
        sys,
        "argv",
        ["crawler.py", "--keyword", "Demo Shop", "--max-results", "1", "--service-task-id", "123"],
    )
    monkeypatch.setattr(ptt_crawler, "scrape_ptt", fake_scrape)
    monkeypatch.setattr("adapters.ptt.local_buffer.write_ptt_buffer", fake_buffer)
    monkeypatch.setattr(ptt_crawler.db, "save_ptt_posts_with_result", fake_save)

    result = await ptt_crawler.main()

    assert calls == ["buffer", "db"]
    assert set(result) == {
        "platform",
        "status",
        "inserted",
        "outcome",
        "technical_success",
        "data_yield_success",
        "cards_found",
        "comments_found",
        "canonical_posts_written",
        "canonical_comments_written",
        "post_metric_snapshots_written",
        "comment_metric_snapshots_written",
        "persistence",
        "elapsed",
        "error_type",
        "error_message",
        "buffer_path",
        "diagnostics",
        "ai_items_enqueued",
    }
    assert result["status"] == "success"
    assert result["inserted"] == 1
    assert result["comments_found"] == 0
    assert result["buffer_path"] == str(tmp_path / "buffer.jsonl")
    assert result["diagnostics"]["buffer"]["written"] is True
    assert result["diagnostics"]["error"]["type"] is None


@pytest.mark.asyncio
async def test_ptt_main_returns_failed_when_buffer_write_fails(monkeypatch):
    calls = []

    async def fake_scrape(query, *, max_results, args, diagnostics=None):
        return [_fake_ptt_post()]

    def fake_buffer(posts, *, query, crawl_job_id=None, service_task_id=None):
        calls.append("buffer")
        raise OSError("buffer disk unavailable")

    def fake_save(posts):
        calls.append("db")
        return PersistenceResult([PersistenceStageResult("canonical_posts", True, len(posts), len(posts))])

    monkeypatch.setattr(sys, "argv", ["crawler.py", "--keyword", "Demo Shop", "--max-results", "1"])
    monkeypatch.setattr(ptt_crawler, "scrape_ptt", fake_scrape)
    monkeypatch.setattr("adapters.ptt.local_buffer.write_ptt_buffer", fake_buffer)
    monkeypatch.setattr(ptt_crawler.db, "save_ptt_posts_with_result", fake_save)

    result = await ptt_crawler.main()

    assert calls == ["buffer"]
    assert result["status"] == "failed"
    assert result["inserted"] == 0
    assert result["comments_found"] == 0
    assert result["error_type"] == "buffer_write_failed"
    assert "buffer disk unavailable" in result["error_message"]
    assert result["buffer_path"] is None
    assert result["diagnostics"]["error"]["recoverable"] is True


@pytest.mark.asyncio
async def test_ptt_main_returns_partial_success_when_db_write_fails_after_buffer(monkeypatch, tmp_path):
    calls = []

    async def fake_scrape(query, *, max_results, args, diagnostics=None):
        return [_fake_ptt_post()]

    def fake_buffer(posts, *, query, crawl_job_id=None, service_task_id=None):
        calls.append("buffer")
        path = tmp_path / "buffer.jsonl"
        path.write_text("{}", encoding="utf-8")
        return path

    def fake_save(posts):
        calls.append("db")
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(sys, "argv", ["crawler.py", "--keyword", "Demo Shop", "--max-results", "1"])
    monkeypatch.setattr(ptt_crawler, "scrape_ptt", fake_scrape)
    monkeypatch.setattr("adapters.ptt.local_buffer.write_ptt_buffer", fake_buffer)
    monkeypatch.setattr(ptt_crawler.db, "save_ptt_posts_with_result", fake_save)

    result = await ptt_crawler.main()

    assert calls == ["buffer", "db"]
    assert result["status"] == "partial_success"
    assert result["inserted"] == 0
    assert result["comments_found"] == 0
    assert result["error_type"] == "db_write_failed"
    assert "db unavailable" in result["error_message"]
    assert result["buffer_path"] == str(tmp_path / "buffer.jsonl")
    assert result["diagnostics"]["error"]["recoverable"] is True


@pytest.mark.asyncio
async def test_ptt_main_reports_comments_found_for_crawl_job_summary(monkeypatch, tmp_path):
    post = _fake_ptt_post()
    post["comments"] = [
        {"content": "first", "comment_type": "push"},
        {"content": "second", "comment_type": "arrow"},
    ]

    async def fake_scrape(query, *, max_results, args, diagnostics=None):
        return [post]

    def fake_buffer(posts, *, query, crawl_job_id=None, service_task_id=None):
        path = tmp_path / "buffer.jsonl"
        path.write_text("{}", encoding="utf-8")
        return path

    monkeypatch.setattr(sys, "argv", ["crawler.py", "--keyword", "Demo Shop", "--max-results", "1", "--dry-run"])
    monkeypatch.setattr(ptt_crawler, "scrape_ptt", fake_scrape)
    monkeypatch.setattr("adapters.ptt.local_buffer.write_ptt_buffer", fake_buffer)

    result = await ptt_crawler.main()

    assert result["comments_found"] == 2


def test_command_module_crawler_omits_default_board_from_argv():
    args = Namespace(
        headless="True",
        max_scroll=1,
        max_minutes=1,
        date_range="all",
        service_type="reputation_query",
        schedule_type="once",
        channel="cli",
        engine="duckduckgo",
        max_results=3,
        client_name="demo-client",
        business_name="Demo Shop",
        keyword="Demo Shop",
        client_id=None,
        business_id=None,
        since_days=None,
        start_date=None,
        end_date=None,
        url=None,
        service_task_id=None,
        crawl_job_id=None,
        line_user_id=None,
        source_message_id=None,
        site=None,
        searxng_url=None,
        keep_unknown_time=False,
        dry_run=True,
        board=None,
    )

    argv = CommandModuleCrawler("ptt", "adapters.ptt.crawler")._build_argv(args)

    assert "--board" not in argv
    assert "Food" not in argv
