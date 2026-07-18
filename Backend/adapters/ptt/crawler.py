from __future__ import annotations

import argparse
import asyncio
import os
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

import random
import aiohttp
from urllib.error import HTTPError, URLError

import core.cli as cli
import core.logger as logger_mod
import core.supabase as db
import core.time_filter as time_filter
from core.http_client import fetch_text
from core.anti_block import CrawlPolicy, RateLimiter
from core.query import build_query_attempts, contains_business_name
from core.rolling_delta import rolling_window, unlimited_or_positive
from core.search_config import load_config
from core.search_engines import create_engine, engine_names_for
from core.search_models import SearchQuery
from adapters.ptt.parser import parse_ptt_index_html
from adapters.ptt.config import (
    DEFAULT_PTT_FALLBACK_BOARDS,
    PTT_QUERY_MATCH_MIN_RATIO,
    PTT_FETCH_ATTEMPTS,
    PTT_RETRY_BASE_DELAY_SECONDS,
    PTT_RETRY_MAX_DELAY_SECONDS,
    PTT_RETRY_JITTER_MIN_SECONDS,
    PTT_RETRY_JITTER_MAX_SECONDS,
    PTT_ARTICLE_DELAY_MIN_SECONDS,
    PTT_ARTICLE_DELAY_MAX_SECONDS,
    PTT_BOARD_DELAY_MIN_SECONDS,
    PTT_BOARD_DELAY_MAX_SECONDS,
    RETRYABLE_HTTP_STATUS,
    NON_RETRYABLE_HTTP_STATUS,
    PTT_INDEX_SCAN_MAX_PAGES,
    PTT_INDEX_SCAN_MAX_RESULTS_PER_BOARD,
    PTT_QUERY_VARIANT_LIMIT,
    PTT_MIN_RELEVANCE_SCORE,
    PTT_CACHE_TTL_HOURS,
)
from adapters.ptt.rules import classify_rule_based_signals
from adapters.ptt.delta import classify_ptt_posts, normalize_ptt_url

logger = logger_mod.get_logger("adapters.ptt")
PTT_ARTICLE_RE = re.compile(r"^/bbs/(?P<board>[^/]+)/(?P<external_id>M\.[^/]+\.html)$")
PTT_OVER18_HEADERS = {"Cookie": "over18=1"}
PTT_ERROR_TYPES = {
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


def normalize_search_keyword(value: str | None) -> str:
    return str(value or "").strip().strip('"').strip("'").strip()


class PTTSearchParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[dict] = []
        self._current: dict | None = None
        self._depth = 0
        self._field: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = attr.get("class", "")
        if tag == "div" and "r-ent" in classes:
            self._current = {"title": "", "author_name": "", "post_time_raw": "", "post_url": ""}
            self._depth = 1
            return
        if not self._current:
            return
        if tag == "div":
            self._depth += 1
            if "title" in classes:
                self._field = "title"
            elif "author" in classes:
                self._field = "author_name"
            elif "date" in classes:
                self._field = "post_time_raw"
        elif tag == "a" and self._field == "title":
            href = attr.get("href")
            if href:
                self._current["post_url"] = f"https://www.ptt.cc{href}" if href.startswith("/") else href

    def handle_data(self, data: str) -> None:
        if self._current and self._field:
            self._current[self._field] += data

    def handle_endtag(self, tag: str) -> None:
        if not self._current:
            return
        if tag == "div":
            if self._field:
                self._field = None
            self._depth -= 1
            if self._depth <= 0:
                item = {key: " ".join(str(value).split()) for key, value in self._current.items()}
                if item.get("post_url") and item.get("title"):
                    self.items.append(item)
                self._current = None


async def _polite_sleep(min_seconds: float, max_seconds: float) -> None:
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))


def _fetch_text_with_retry(
    url: str,
    *,
    params: dict[str, str | int | None] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    attempts: int = PTT_FETCH_ATTEMPTS,
    diagnostics: dict | None = None,
) -> str:
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            return fetch_text(url, params=params, headers=headers, timeout=timeout)
        except HTTPError as exc:
            if exc.code in NON_RETRYABLE_HTTP_STATUS:
                logger.warning(
                    "PTT fetch non-retryable HTTP error: url=%s status=%s",
                    url,
                    exc.code,
                )
                raise
            if exc.code not in RETRYABLE_HTTP_STATUS:
                logger.warning(
                    "PTT fetch unexpected HTTP error: url=%s status=%s",
                    url,
                    exc.code,
                )
                raise
            last_error = exc
        except (TimeoutError, ConnectionResetError, URLError) as exc:
            last_error = exc

        if attempt >= attempts - 1:
            break

        if diagnostics is not None:
            diagnostics["fetch"]["retry_count"] += 1

        delay = min(
            PTT_RETRY_MAX_DELAY_SECONDS,
            PTT_RETRY_BASE_DELAY_SECONDS * (2 ** attempt),
        ) + random.uniform(
            PTT_RETRY_JITTER_MIN_SECONDS,
            PTT_RETRY_JITTER_MAX_SECONDS,
        )
        logger.warning(
            "PTT fetch retry: url=%s attempt=%s/%s delay=%.2fs error=%s",
            url,
            attempt + 1,
            attempts,
            delay,
            last_error,
        )
        time.sleep(delay)

    raise last_error or RuntimeError("PTT fetch failed without explicit exception")


async def _fetch_text_with_retry_async(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
    attempts: int = PTT_FETCH_ATTEMPTS,
    diagnostics: dict | None = None,
) -> str:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status in NON_RETRYABLE_HTTP_STATUS:
                    response.raise_for_status()
                if response.status >= 400:
                    response.raise_for_status()
                return await response.text(errors="replace")
        except aiohttp.ClientResponseError as exc:
            if exc.status in NON_RETRYABLE_HTTP_STATUS or exc.status not in RETRYABLE_HTTP_STATUS:
                raise
            last_error = exc
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_error = exc

        if attempt >= attempts - 1:
            break
        if diagnostics is not None:
            diagnostics["fetch"]["retry_count"] += 1
        delay = min(
            PTT_RETRY_MAX_DELAY_SECONDS,
            PTT_RETRY_BASE_DELAY_SECONDS * (2 ** attempt),
        ) + random.uniform(
            PTT_RETRY_JITTER_MIN_SECONDS,
            PTT_RETRY_JITTER_MAX_SECONDS,
        )
        logger.warning(
            "PTT async fetch retry: url=%s attempt=%s/%s delay=%.2fs error=%s",
            url,
            attempt + 1,
            attempts,
            delay,
            last_error,
        )
        await asyncio.sleep(delay)
    raise last_error or RuntimeError("PTT async fetch failed without explicit exception")


def _query_variants(query: str, business_name: str | None = None, keyword: str | None = None) -> list[str]:
    """Build discovery variants that always retain the business identity."""

    query = normalize_search_keyword(query)
    business_name = normalize_search_keyword(business_name)
    keyword = normalize_search_keyword(keyword)
    variants = (
        build_query_attempts(business_name=business_name, keyword=keyword)
        if business_name
        else [query]
    )

    output: list[str] = []
    for variant in variants:
        normalized = " ".join(variant.split())
        if normalized and normalized not in output:
            output.append(normalized)
    return output[:PTT_QUERY_VARIANT_LIMIT]


def _parse_prev_page_url(html: str) -> str | None:
    match = re.search(r'href="([^"]+)"[^>]*>[^<]*\u4e0a\u9801', html)
    if match:
        return f"https://www.ptt.cc{match.group(1)}"
    return None


def _deadline_reached(deadline: float | None) -> bool:
    return deadline is not None and time.monotonic() >= deadline


def _timeout_for_deadline(deadline: float | None, default: int = 20) -> int:
    if deadline is None:
        return default
    remaining = max(1.0, deadline - time.monotonic())
    return max(1, min(default, int(remaining)))


def _title_matches_query(title: str, query: str, business_name: str | None = None, input_keyword: str | None = None) -> bool:
    if business_name:
        return contains_business_name(title, business_name)

    title_lower = title.casefold()
    if query and query.casefold() in title_lower:
        return True
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return False
    matched = sum(1 for term in terms if term in title_lower)
    return (matched / len(terms)) >= PTT_QUERY_MATCH_MIN_RATIO


async def _discover_board_index_urls_multi_variants(
    query: str,
    board: str,
    max_pages: int,
    max_results: int,
    business_name: str | None,
    input_keyword: str | None,
    variants: list[str],
    deadline: float | None = None,
    diagnostics: dict | None = None,
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    
    current_url = f"https://www.ptt.cc/bbs/{quote(board, safe='')}/index.html"
    
    for page_idx in range(max_pages):
        if _deadline_reached(deadline):
            break
        if page_idx > 0:
            await _polite_sleep(
                PTT_BOARD_DELAY_MIN_SECONDS,
                PTT_BOARD_DELAY_MAX_SECONDS,
            )
            
        try:
            html = await asyncio.to_thread(
                _fetch_text_with_retry,
                current_url,
                headers=PTT_OVER18_HEADERS,
                timeout=_timeout_for_deadline(deadline),
                attempts=1 if deadline is not None else PTT_FETCH_ATTEMPTS,
                diagnostics=diagnostics,
            )
        except Exception as exc:
            logger.warning("PTT index scan failed to fetch url %s: %s", current_url, exc)
            break
            
        for item in parse_ptt_index_html(html):
            title = item.get("title", "")
            post_url = item.get("post_url", "")
            if not title or not post_url:
                continue
                
            normalized = normalize_ptt_article_url(post_url)
            if not normalized or normalized in seen:
                continue
                
            matched = False
            for var in variants:
                if _title_matches_query(title, query=var, business_name=business_name, input_keyword=input_keyword):
                    matched = True
                    break
            
            if matched:
                seen.add(normalized)
                urls.append(normalized)
                if len(urls) >= max_results:
                    break
                    
        if len(urls) >= max_results:
            break
            
        prev_url = _parse_prev_page_url(html)
        if not prev_url:
            break
        current_url = prev_url
        
    return urls[:max_results]


async def discover_ptt_urls(
    query: str,
    max_results: int,
    args,
    diagnostics: dict | None = None,
    deadline: float | None = None,
) -> list[str]:
    """Find public PTT article URLs for a global keyword query."""
    
    # 1. Determine query variants
    input_keyword = getattr(args, "input_keyword", None)
    business_name = getattr(args, "business_name", None)
    variants = _query_variants(query, business_name=business_name, keyword=input_keyword)
    
    if diagnostics is not None:
        diagnostics["discovery"]["query_variants"] = list(variants)
        
    urls: list[str] = []
    seen: set[str] = set()
    
    config = load_config(searxng_url=getattr(args, "searxng_url", None))
    
    # Track diagnostic info
    engines_tried = []
    fallback_boards_tried = []
    index_boards_tried = []
    
    # 1. Global search engine discovery
    for engine_name in engine_names_for(getattr(args, "engine", "duckduckgo"), config):
        if _deadline_reached(deadline):
            args.ptt_deadline_reached = True
            break
        engines_tried.append(engine_name)
        for variant in variants:
            if _deadline_reached(deadline):
                args.ptt_deadline_reached = True
                break
            remaining = max_results - len(urls)
            if remaining <= 0:
                break
            search_text = f'site:ptt.cc/bbs "{variant}"'
            try:
                engine = create_engine(engine_name, config)
                results = await engine.search(
                    SearchQuery(
                        keyword=search_text,
                        engine=engine_name,
                        max_results=max(remaining * 3, remaining),
                    )
                )
                for result in results:
                    normalized = normalize_ptt_article_url(result.url)
                    if not normalized or normalized in seen:
                        continue
                    if getattr(args, "board", None) and ptt_url_metadata(normalized).get("board") != args.board:
                        continue
                    seen.add(normalized)
                    urls.append(normalized)
                    logger.info("PTT URL discovered via engine:%s", engine_name)
                    if len(urls) >= max_results:
                        break
            except Exception as exc:
                logger.warning("Search engine %s failed during PTT discovery: %s", engine_name, exc)
                
    # 2. Board search fallback (specified board)
    if not urls and getattr(args, "board", None):
        board = args.board
        fallback_boards_tried.append(board)
        logger.info("PTT board fallback started")
        for variant in variants:
            if _deadline_reached(deadline):
                args.ptt_deadline_reached = True
                break
            remaining = max_results - len(urls)
            if remaining <= 0:
                break
            try:
                board_urls = await asyncio.to_thread(
                    _discover_board_search_urls,
                    variant,
                    board,
                    remaining,
                    timeout=_timeout_for_deadline(deadline),
                    attempts=1 if deadline is not None else PTT_FETCH_ATTEMPTS,
                    diagnostics=diagnostics,
                )
                for url in board_urls:
                    normalized = normalize_ptt_article_url(url)
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        urls.append(normalized)
                        logger.info("PTT URL discovered via board:%s", board)
                        if len(urls) >= max_results:
                            break
            except Exception as exc:
                logger.warning("PTT board search failed on board %s with variant %s: %s", board, variant, exc)
        logger.info("PTT board fallback completed")
        
    # 3. Board search fallback (default boards)
    elif not urls:
        logger.info("PTT board fallback started")
        first_search = True
        for board in DEFAULT_PTT_FALLBACK_BOARDS:
            if _deadline_reached(deadline):
                args.ptt_deadline_reached = True
                break
            fallback_boards_tried.append(board)
            board_found = False
            for variant in variants:
                if _deadline_reached(deadline):
                    args.ptt_deadline_reached = True
                    break
                remaining = max_results - len(urls)
                if remaining <= 0:
                    break
                if not first_search:
                    await _polite_sleep(
                        PTT_BOARD_DELAY_MIN_SECONDS,
                        PTT_BOARD_DELAY_MAX_SECONDS,
                    )
                first_search = False
                try:
                    board_urls = await asyncio.to_thread(
                        _discover_board_search_urls,
                        variant,
                        board,
                        remaining,
                        timeout=_timeout_for_deadline(deadline),
                        attempts=1 if deadline is not None else PTT_FETCH_ATTEMPTS,
                        diagnostics=diagnostics,
                    )
                    for url in board_urls:
                        normalized = normalize_ptt_article_url(url)
                        if normalized and normalized not in seen:
                            seen.add(normalized)
                            urls.append(normalized)
                            board_found = True
                            logger.info("PTT URL discovered via board:%s", board)
                            if len(urls) >= max_results:
                                break
                except Exception as exc:
                    logger.warning("PTT board fallback search failed on board %s: %s", board, exc)
                if board_found:
                    pass
            if len(urls) >= max_results:
                break
        logger.info("PTT board fallback completed")
        
    # 4. Board index scan fallback (if still no urls found)
    if not urls:
        logger.info("PTT board index scan fallback started")
        first_scan = True
        boards_to_scan = [args.board] if getattr(args, "board", None) else DEFAULT_PTT_FALLBACK_BOARDS
        for board in boards_to_scan:
            if _deadline_reached(deadline):
                args.ptt_deadline_reached = True
                break
            index_boards_tried.append(board)
            remaining = max_results - len(urls)
            if remaining <= 0:
                break
            if not first_scan:
                await _polite_sleep(
                    PTT_BOARD_DELAY_MIN_SECONDS,
                    PTT_BOARD_DELAY_MAX_SECONDS,
                )
            first_scan = False
            try:
                board_urls = await _discover_board_index_urls_multi_variants(
                    query=query,
                    board=board,
                    max_pages=_ptt_effective_page_limit(args),
                    max_results=remaining,
                    business_name=business_name,
                    input_keyword=input_keyword,
                    variants=variants,
                    deadline=deadline,
                    diagnostics=diagnostics,
                )
                for url in board_urls:
                    normalized = normalize_ptt_article_url(url)
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        urls.append(normalized)
                        logger.info("PTT URL discovered via board index scan:%s: %s", board, normalized)
                        if len(urls) >= max_results:
                            break
            except Exception as exc:
                logger.warning("PTT board index scan failed on board %s: %s", board, exc)
            if len(urls) >= max_results:
                break
        logger.info("PTT board index scan fallback completed")
        
    if diagnostics is not None:
        diagnostics["discovery"]["engines_tried"] = list(engines_tried)
        diagnostics["discovery"]["query_variants"] = list(variants)
        diagnostics["discovery"]["fallback_boards_tried"] = list(fallback_boards_tried)
        diagnostics["discovery"]["index_boards_tried"] = list(index_boards_tried)
        diagnostics["discovery"]["urls_discovered"] = len(seen)
        diagnostics["discovery"]["duplicate_urls_removed"] = len(seen) - len(urls)
        diagnostics["discovery"]["urls_after_dedupe"] = len(urls)
        
    return urls[:max_results]


def normalize_ptt_article_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc not in {"www.ptt.cc", "ptt.cc"}:
        return None
    match = PTT_ARTICLE_RE.match(parsed.path)
    if not match:
        return None
    return f"https://www.ptt.cc{parsed.path}"


def ptt_url_metadata(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    match = PTT_ARTICLE_RE.match(parsed.path)
    return match.groupdict() if match else {}


def _discover_board_search_urls(
    query: str,
    board: str,
    max_results: int,
    diagnostics: dict | None = None,
    timeout: int = 20,
    attempts: int = PTT_FETCH_ATTEMPTS,
) -> list[str]:
    url = f"https://www.ptt.cc/bbs/{quote(board, safe='')}/search"
    html = _fetch_text_with_retry(
        url,
        params={"q": query},
        headers=PTT_OVER18_HEADERS,
        timeout=timeout,
        attempts=attempts,
        diagnostics=diagnostics,
    )
    return [
        normalized
        for item in parse_ptt_index_html(html)
        if (normalized := normalize_ptt_article_url(item.get("post_url", "")))
    ][:max_results]


def _score_ptt_article(
    article: dict,
    *,
    query: str,
    business_name: str | None = None,
    input_keyword: str | None = None,
) -> float:
    title = article.get("title") or ""
    content = article.get("content") or title
    
    score = 0.0
    
    title_lower = title.casefold()
    content_lower = content.casefold()
    
    # title matches
    if business_name and business_name.casefold() in title_lower:
        score += 5
    if input_keyword and input_keyword.casefold() in title_lower:
        score += 3
    if query and query.casefold() in title_lower:
        score += 3
        
    # content matches
    if business_name and business_name.casefold() in content_lower:
        score += 4
    if input_keyword and input_keyword.casefold() in content_lower:
        score += 2
    if query and query.casefold() in content_lower:
        score += 2
        
    # token ratio match
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms and query.strip():
        terms = [query.strip().casefold()]
        
    token_match_ratio = 0.0
    if terms:
        matched = sum(1 for term in terms if term in content_lower)
        token_match_ratio = matched / len(terms)
        
    score += token_match_ratio * 3
    
    # engagement
    comment_count = article.get("comment_count") or 0
    score += min(comment_count, 50) / 10
    
    # PTT net sentiment is not relevance, but can break ties slightly
    ptt_net_score = article.get("ptt_net_score") or 0
    score += max(min(ptt_net_score, 10), -10) / 100
    
    return score


def _article_matches_business(article: dict, business_name: str | None) -> bool:
    if not business_name:
        return True
    return contains_business_name(
        f"{article.get('title') or ''}\n{article.get('content') or ''}",
        business_name,
    )


async def scrape_ptt(
    query: str,
    *,
    max_results: int,
    args,
    diagnostics: dict | None = None,
    deadline: float | None = None,
) -> list[dict]:
    candidate_max = max_results
    try:
        if diagnostics is not None:
            urls = await discover_ptt_urls(
                query,
                candidate_max,
                args,
                diagnostics=diagnostics,
                deadline=deadline,
            )
        else:
            urls = await discover_ptt_urls(query, candidate_max, args, deadline=deadline)
    except TypeError:
        urls = await discover_ptt_urls(query, candidate_max, args)
    if deadline is not None and time.monotonic() >= deadline:
        args.ptt_deadline_reached = True
        return []
    if diagnostics is not None:
        diagnostics["discovery"]["article_urls_discovered"] = len(urls)
        diagnostics["discovery"]["article_urls_validated"] = len(
            [url for url in urls if normalize_ptt_article_url(url)]
        )
        
    posts = []

    business_name = getattr(args, "business_name", None)
    input_keyword = getattr(args, "input_keyword", None)

    policy = CrawlPolicy.load()
    concurrency = min(2, policy.for_platform("ptt").max_concurrency)
    semaphore = asyncio.Semaphore(concurrency)
    rate_limiter = RateLimiter(policy)

    async def fetch_candidate(session: aiohttp.ClientSession, url: str) -> tuple[str, dict]:
        metadata = ptt_url_metadata(url)
        board = metadata.get("board")
        if deadline is not None and time.monotonic() >= deadline:
            args.ptt_deadline_reached = True
            return url, {}
        async with semaphore:
            if deadline is not None and time.monotonic() >= deadline:
                args.ptt_deadline_reached = True
                return url, {}
            await rate_limiter.acquire("ptt", action="article_fetch")
            if deadline is not None and time.monotonic() >= deadline:
                args.ptt_deadline_reached = True
                return url, {}
            request_timeout = 20
            if deadline is not None:
                request_timeout = max(1, min(20, int(deadline - time.monotonic())))
            article = await _fetch_article_async(
                session,
                url,
                board_arg=board,
                diagnostics=diagnostics,
                timeout=request_timeout,
            )
        return url, article

    async with aiohttp.ClientSession() as session:
        fetched = await asyncio.gather(*(fetch_candidate(session, url) for url in urls))

    for url, article in fetched:
        if not article:
            continue
        if not article.get("title") and not article.get("content"):
            continue
        post_time = article.get("post_time")
        post_time_raw = article.get("post_time_raw")
        if not time_filter.should_keep_post(post_time, post_time_raw or "", args, "ptt"):
            if diagnostics is not None:
                diagnostics["filter"]["date_rejected"] += 1
            continue

        if not _article_matches_business(article, business_name):
            if diagnostics is not None:
                diagnostics["filter"]["business_rejected"] += 1
            continue
            
        score = _score_ptt_article(
            article,
            query=query,
            business_name=business_name,
            input_keyword=input_keyword,
        )
        article["relevance_score"] = round(score, 4)
        article["raw_json"]["relevance_score"] = round(score, 4)
        
        if diagnostics is not None:
            diagnostics["filter"]["candidate_posts"] += 1
            
        if score < PTT_MIN_RELEVANCE_SCORE:
            logger.debug(
                "PTT article skipped by relevance score: score=%.2f limit=%.2f url=%s",
                score,
                PTT_MIN_RELEVANCE_SCORE,
                url,
            )
            if diagnostics is not None:
                diagnostics["filter"]["dropped_by_relevance"] += 1
            continue
            
        if diagnostics is not None:
            diagnostics["filter"]["kept_posts"] += 1
            
        article["keyword"] = query
        posts.append(article)
        
    posts.sort(key=lambda x: x["relevance_score"], reverse=True)
    return posts[:max_results]


def _fetch_article(url: str, board_arg: str | None = None, diagnostics: dict | None = None) -> dict:
    from adapters.ptt.cache import get_cached_article, set_cached_article, is_quarantined, quarantine_url
    
    if is_quarantined(url, diagnostics=diagnostics):
        logger.debug("PTT URL skipped (quarantined): %s", url)
        return {}
        
    cached = get_cached_article(url, diagnostics=diagnostics)
    if cached:
        logger.debug("PTT URL cache hit: %s", url)
        return cached
        
    if diagnostics is not None:
        diagnostics["fetch"]["attempted"] += 1
        
    try:
        html = _fetch_text_with_retry(
            url, 
            headers=PTT_OVER18_HEADERS,
            timeout=20,
            diagnostics=diagnostics,
        )
    except Exception as exc:
        logger.debug("PTT article fetch failed: url=%s error=%s", url, exc)
        if diagnostics is not None:
            diagnostics["fetch"]["failed"] += 1
            diagnostics["fetch"]["last_error_type"] = _fetch_error_type(exc)
            diagnostics["fetch"]["last_error_message"] = str(exc)
        
        reason = "fetch_failed"
        from urllib.error import HTTPError
        if isinstance(exc, HTTPError):
            reason = f"HTTP_{exc.code}"
        quarantine_url(url, reason, diagnostics=diagnostics)
        return {}
        
    if diagnostics is not None:
        diagnostics["fetch"]["success"] += 1
        
    article = parse_ptt_article_html(html, url=url, board_arg=board_arg)
    
    is_abnormal = False
    reasons = []
    
    if not article.get("title") and not article.get("content"):
        is_abnormal = True
        reasons.append("no_title_and_no_content")
    if article.get("parser_warnings"):
        is_abnormal = True
        reasons.append("incomplete_metadata")
        
    if is_abnormal:
        try:
            from adapters.ptt.snapshot import save_html_snapshot
            save_html_snapshot(html, external_id=article.get("external_id"))
            if diagnostics is not None:
                diagnostics["parse"]["snapshots_saved"] += 1
        except Exception as exc:
            logger.warning("Failed to invoke save_html_snapshot: %s", exc)
            
    if article.get("title") or article.get("content"):
        set_cached_article(url, article, diagnostics=diagnostics)
        if diagnostics is not None:
            diagnostics["parse"]["success"] += 1
    else:
        if diagnostics is not None:
            diagnostics["parse"]["failed"] += 1
            
    return article


async def _fetch_article_async(
    session: aiohttp.ClientSession,
    url: str,
    *,
    board_arg: str | None = None,
    diagnostics: dict | None = None,
    timeout: int = 20,
) -> dict:
    from adapters.ptt.cache import get_cached_article, set_cached_article, is_quarantined, quarantine_url

    if is_quarantined(url, diagnostics=diagnostics):
        return {}
    cached = get_cached_article(url, diagnostics=diagnostics)
    if cached:
        return cached
    if diagnostics is not None:
        diagnostics["fetch"]["attempted"] += 1

    try:
        html = await _fetch_text_with_retry_async(
            session,
            url,
            headers=PTT_OVER18_HEADERS,
            timeout=timeout,
            diagnostics=diagnostics,
        )
    except Exception as exc:
        if diagnostics is not None:
            diagnostics["fetch"]["failed"] += 1
            diagnostics["fetch"]["last_error_type"] = _fetch_error_type(exc)
            diagnostics["fetch"]["last_error_message"] = str(exc)
        status = getattr(exc, "status", None)
        quarantine_url(url, f"HTTP_{status}" if status else "fetch_failed", diagnostics=diagnostics)
        return {}

    if diagnostics is not None:
        diagnostics["fetch"]["success"] += 1
    article = parse_ptt_article_html(html, url=url, board_arg=board_arg)
    abnormal = not article.get("title") and not article.get("content")
    abnormal = abnormal or bool(article.get("parser_warnings"))
    if abnormal:
        try:
            from adapters.ptt.snapshot import save_html_snapshot

            save_html_snapshot(html, external_id=article.get("external_id"))
            if diagnostics is not None:
                diagnostics["parse"]["snapshots_saved"] += 1
        except Exception as exc:
            logger.warning("Failed to save async PTT HTML snapshot: %s", exc)

    if article.get("title") or article.get("content"):
        set_cached_article(url, article, diagnostics=diagnostics)
        if diagnostics is not None:
            diagnostics["parse"]["success"] += 1
    elif diagnostics is not None:
        diagnostics["parse"]["failed"] += 1
    return article


def parse_ptt_article_html(html: str, *, url: str, board_arg: str | None = None) -> dict:
    metadata = ptt_url_metadata(url)
    
    meta_values = re.findall(r'<span class="article-meta-value">(.*?)</span>', html, flags=re.S)
    warnings = []
    
    # Author
    author_raw = ""
    if len(meta_values) > 0:
        author_raw = _strip_html(meta_values[0])
    else:
        warnings.append("Author missing from metadata, using regex fallback")
        author_match = re.search(r'作者\s*:\s*([^\s(]+)(?:\s*\((.*?)\))?', html)
        if author_match:
            author_id = author_match.group(1)
            author_name = author_match.group(2) or author_id
            author_raw = f"{author_id} ({author_name})"
            
    # Title
    title = ""
    if len(meta_values) > 2:
        title = _strip_html(meta_values[2])
    else:
        warnings.append("Title missing from metadata, using <title> fallback")
        title_match = re.search(r'<title>(.*?)</title>', html, flags=re.I | re.S)
        if title_match:
            title_text = _strip_html(title_match.group(1))
            for suffix in ["- 批踢踢實業坊", "- 看板"]:
                if suffix in title_text:
                    title_text = title_text.split(suffix)[0].strip()
            title = title_text
            
    # Post Time Raw
    post_time_raw = ""
    if len(meta_values) > 3:
        post_time_raw = _strip_html(meta_values[3])
    else:
        warnings.append("Post time missing from metadata, using regex fallback")
        time_match = re.search(r'時間\s*:\s*(.*?)(?:\n|$|<)', html)
        if time_match:
            post_time_raw = _strip_html(time_match.group(1))
            
    # Content
    content = ""
    try:
        content = _extract_article_content(html)
    except Exception as exc:
        warnings.append(f"Content extraction failed: {exc}")
        content = _strip_html(html)
        
    if not content:
        warnings.append("Content extraction returned empty, using fallback")
        content = _strip_html(html)
        
    # Board
    board = metadata.get("board")
    if not board:
        warnings.append("Board missing from URL metadata, using board_arg fallback")
        board = board_arg
        
    # External ID
    external_id = metadata.get("external_id")
    if not external_id:
        warnings.append("External ID missing from URL metadata, using URL basename fallback")
        parsed_url = urlparse(url)
        external_id = Path(parsed_url.path).name if parsed_url.path else "unknown"

    # Comments
    comments = []
    try:
        comments = _parse_push_comments(html)
    except Exception as exc:
        warnings.append(f"Comment parsing failed: {exc}")

    push_count = sum(1 for comment in comments if comment["comment_type"] == "push")
    boo_count = sum(1 for comment in comments if comment["comment_type"] == "boo")
    arrow_count = sum(1 for comment in comments if comment["comment_type"] == "arrow")
    comment_count = push_count + boo_count + arrow_count
    normalized_score = 0.5 if comment_count == 0 else (push_count + 0.5 * arrow_count) / comment_count
    
    ptt_metrics = {
        "push_count": push_count,
        "boo_count": boo_count,
        "arrow_count": arrow_count,
        "comment_count": comment_count,
        "ptt_net_score": push_count - boo_count,
        "normalized_score": round(normalized_score, 4),
    }
    
    author_name, author_id = _parse_author(author_raw)
    post_time = _parse_ptt_time(post_time_raw)
    
    raw_json = {
        "platform": "ptt",
        "post_time_raw": post_time_raw,
        "board": board,
        "ptt_metrics": ptt_metrics,
        "parser_warnings": list(warnings),
        "raw_json": {
            "url": url,
            "author_raw": author_raw,
        },
    }
    
    article = {
        "source_url": url,
        "post_url": url,
        "external_id": external_id,
        "board": board,
        "author_name": author_name,
        "author_id": author_id,
        "title": title,
        "content": content,
        "post_time_raw": post_time_raw,
        "post_time": post_time,
        "comments": comments,
        "like_count": push_count,
        "comment_count": comment_count,
        "reaction_count": comment_count,
        "push_count": push_count,
        "boo_count": boo_count,
        "arrow_count": arrow_count,
        "ptt_net_score": push_count - boo_count,
        "normalized_score": normalized_score,
        "ptt_metrics": ptt_metrics,
        "parser_warnings": list(warnings),
        "source": "ptt",
        "raw_json": raw_json,
    }
    
    # Classify rule based signals
    signals = classify_rule_based_signals(article)
    article.update(signals)
    article["raw_json"].update(signals)
    
    return article


def _parse_push_comments(html: str) -> list[dict]:
    comments = []
    for match in re.finditer(r'<div class="push">(.*?)</div>', html, flags=re.S):
        push_html = match.group(1)
        push_tag = _strip_html(_span_class_text(push_html, "push-tag"))
        push_userid = _strip_html(_span_class_text(push_html, "push-userid"))
        push_content = _strip_html(_span_class_text(push_html, "push-content"))
        push_ipdatetime = _strip_html(_span_class_text(push_html, "push-ipdatetime"))
        content = push_content[1:].strip() if push_content.startswith(":") else push_content
        comment_type = _comment_type_for_push_tag(push_tag)
        comments.append(
            {
                "author_name": push_userid,
                "author_id": push_userid,
                "content": content,
                "comment_type": comment_type,
                "comment_time_raw": push_ipdatetime,
                "commented_at": None,
                "like_count": 0,
                "reply_count": None,
                "reaction_count": None,
                "raw_json": {
                    "push_tag": push_tag,
                    "push_userid": push_userid,
                    "push_content": push_content,
                    "push_ipdatetime": push_ipdatetime,
                },
            }
        )
    return comments


def _query_matches_content(
    query: str,
    content: str,
    *,
    min_ratio: float = PTT_QUERY_MATCH_MIN_RATIO,
) -> bool:
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms and query.strip():
        terms = [query.strip().casefold()]

    if not terms:
        return True

    haystack = content.casefold()
    matched = sum(1 for term in terms if term in haystack)
    ratio = matched / len(terms)

    if ratio < min_ratio:
        logger.debug(
            "PTT article skipped by keyword ratio: matched=%s total=%s ratio=%.2f query=%s",
            matched,
            len(terms),
            ratio,
            query,
        )
        return False

    return True


def _comment_type_for_push_tag(push_tag: str) -> str:
    normalized = push_tag.strip()
    if normalized == "推":
        return "push"
    if normalized == "噓":
        return "boo"
    return "arrow"


def _extract_article_content(html: str) -> str:
    main_match = re.search(r'<div id="main-content"[^>]*>(.*)', html, flags=re.S)
    body_html = main_match.group(1) if main_match else html
    body_html = body_html.split('<span class="f2">', 1)[0]
    body_html = re.sub(r'<div class="article-metaline.*?</div>', "", body_html, flags=re.S)
    body_html = re.sub(r'<div class="article-metaline-right.*?</div>', "", body_html, flags=re.S)
    body_html = re.sub(r'<div class="push".*?</div>', "", body_html, flags=re.S)
    return _strip_html(body_html)


def _parse_author(author_raw: str) -> tuple[str, str]:
    match = re.match(r"(?P<id>[^\s(]+)\s*(?:\((?P<name>.*?)\))?", author_raw)
    if not match:
        return author_raw, author_raw
    author_id = match.group("id") or author_raw
    author_name = match.group("name") or author_id
    return author_name, author_id


def _span_class_text(value: str, class_name: str) -> str:
    pattern = rf'<span[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>(.*?)</span>'
    match = re.search(pattern, value, flags=re.S)
    return match.group(1) if match else ""


def _strip_html(html: str) -> str:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(unescape(text).split())


def _parse_ptt_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        TAIWAN_TZ = timezone(timedelta(hours=8))
        parsed = datetime.strptime(value.strip(), "%a %b %d %H:%M:%S %Y")
        return parsed.replace(tzinfo=TAIWAN_TZ).astimezone(timezone.utc)
    except ValueError:
        return None


def _build_ptt_parser() -> argparse.ArgumentParser:
    parser_arg = argparse.ArgumentParser(description="PTT Adapter")
    cli.add_common_crawler_args(parser_arg)
    return parser_arg


async def main():
    return await run_from_args(_build_ptt_parser().parse_args())


async def run_from_args(args):
    start_time = time.time()

    logger.info("==========================================")
    logger.info("PTT Adapter start")
    logger.info("query: %s", args.keyword)
    logger.info("board filter: %s", args.board or "<none>")
    logger.info("date range: %s", args.date_range)
    logger.info("==========================================")

    # Initialize structured diagnostics
    diagnostics = {
        "discovery": {
            "engines_tried": [],
            "fallback_boards_tried": [],
            "index_boards_tried": [],
            "query_variants": [],
            "urls_discovered": 0,
            "duplicate_urls_removed": 0,
            "urls_after_dedupe": 0,
            "article_urls_discovered": 0,
            "article_urls_validated": 0,
        },
        "fetch": {
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "retry_count": 0,
            "quarantined": 0,
            "quarantine_skipped": 0,
            "last_error_type": None,
            "last_error_message": None
        },
        "cache": {
            "hit": 0,
            "miss": 0,
            "stale": 0,
            "write_success": 0,
            "write_failed": 0
        },
        "parse": {
            "success": 0,
            "failed": 0,
            "snapshots_saved": 0,
            "warnings": 0
        },
        "filter": {
            "candidate_posts": 0,
            "kept_posts": 0,
            "dropped_by_relevance": 0,
            "business_rejected": 0,
            "keyword_matched": 0,
            "keyword_rejected": 0,
            "date_rejected": 0,
            "min_relevance_score": PTT_MIN_RELEVANCE_SCORE
        },
        "buffer": {
            "written": False,
            "path": None,
            "error": None
        },
        "error": {
            "type": None,
            "message": None,
            "recoverable": None
        }
    }

    if args.lookback_days is not None and args.lookback_days < 0:
        raise ValueError("--lookback-days must be >= 0. Use 0 for an unlimited crawl window.")
    if args.max_minutes <= 0:
        raise ValueError("--max-minutes must be > 0.")

    args.ptt_deadline_reached = False
    crawl_deadline = time.monotonic() + (args.max_minutes * 60)
    post_limit = _ptt_effective_post_limit(args)
    try:
        posts = await scrape_ptt(
            args.keyword,
            max_results=post_limit,
            args=args,
            diagnostics=diagnostics,
            deadline=crawl_deadline,
        )
    except TypeError as exc:
        if "unexpected keyword argument 'deadline'" not in str(exc):
            raise
        posts = await scrape_ptt(
            args.keyword,
            max_results=post_limit,
            args=args,
            diagnostics=diagnostics,
        )
    _sync_ptt_diagnostic_aliases(diagnostics)

    window_start, window_end = rolling_window(lookback_days=args.lookback_days)
    candidate_urls = [normalize_ptt_url(post.get("post_url") or post.get("source_url")) for post in posts]
    existing_index = await asyncio.to_thread(
        db.load_existing_ptt_index,
        window_start,
        window_end,
        candidate_urls=[url for url in candidate_urls if url],
    )
    delta_result = classify_ptt_posts(
        posts,
        existing_index=existing_index,
        window_start=window_start,
        window_end=window_end,
    )
    diagnostics["rolling_delta"] = delta_result["diagnostics"]
    posts = delta_result["posts"]
    for post in posts:
        post["crawl_job_id"] = getattr(args, "crawl_job_id", None)
        post["service_task_id"] = getattr(args, "service_task_id", None)
        if post["post_time"] and isinstance(post["post_time"], datetime):
            post["post_time"] = post["post_time"].isoformat()
            
        # Count warnings from parsed post
        if post.get("parser_warnings"):
            diagnostics["parse"]["warnings"] += len(post["parser_warnings"])
    _sync_ptt_diagnostic_aliases(diagnostics)

    buffer_path = None
    buffer_ok = not posts
    db_error = None
    if posts:
        try:
            from adapters.ptt.local_buffer import write_ptt_buffer
            buffer_path = write_ptt_buffer(
                posts,
                query=args.keyword,
                crawl_job_id=getattr(args, "crawl_job_id", None),
                service_task_id=getattr(args, "service_task_id", None),
            )
            if buffer_path:
                logger.info("PTT local buffer written: path=%s count=%s", buffer_path, len(posts))
                diagnostics["buffer"]["written"] = True
                diagnostics["buffer"]["path"] = str(buffer_path)
                buffer_ok = True
        except Exception as exc:
            logger.warning("PTT local buffer write failed: %s", exc)
            diagnostics["buffer"]["error"] = str(exc)
            _set_error(diagnostics, "buffer_write_failed", str(exc), recoverable=True)

    persistence_result = None
    persistence = {
        "canonical_posts_written": 0,
        "canonical_comments_written": 0,
        "post_metric_snapshots_written": 0,
        "comment_metric_snapshots_written": 0,
        "failed_stages": [],
        "stages": [],
    }
    saved_count = 0
    if posts and buffer_ok and not args.dry_run:
        try:
            persistence_result = await asyncio.to_thread(db.save_ptt_posts_with_result, posts)
            persistence = persistence_result.as_dict()
            saved_count = persistence["canonical_posts_written"]
            diagnostics["rolling_delta"]["db_rows_written"] = saved_count
        except Exception as exc:
            db_error = exc
            logger.warning("PTT DB write failed after local buffer: %s", exc)
            _set_error(diagnostics, "db_write_failed", str(exc), recoverable=True)
    if persistence_result is not None and persistence_result.status != "success":
        db_error = db_error or RuntimeError(persistence_result.error_message or "PTT persistence failed")
        _set_error(
            diagnostics,
            persistence_result.error_type or "db_write_failed",
            persistence_result.error_message,
            recoverable=True,
        )

    status = _ptt_status(posts, buffer_ok=buffer_ok, db_error=db_error, diagnostics=diagnostics)
    error_type = diagnostics["error"]["type"]
    error_message = diagnostics["error"]["message"]
    deadline_reached = bool(getattr(args, "ptt_deadline_reached", False))
    diagnostics["deadline_reached"] = deadline_reached
    if deadline_reached and not posts:
        status = "failed"
        error_type = "timeout"
        error_message = "PTT crawl reached its time budget before collecting data."
    elif deadline_reached and status == "success":
        status = "partial_success"
        error_type = "deadline_reached"
        error_message = "PTT crawl reached its time budget; collected data was preserved."
    comments_found = sum(len(post.get("comments") or []) for post in posts)
    outcome = _ptt_outcome(
        status=status,
        diagnostics=diagnostics,
        canonical_posts_written=persistence["canonical_posts_written"],
        canonical_comments_written=persistence["canonical_comments_written"],
    )

    elapsed_time = time.time() - start_time
    logger.info("==========================================")
    logger.info("PTT Adapter finished")
    logger.info("Total cards found          : %s", len(posts))
    logger.info("Total comments found       : %s", comments_found)
    logger.info("Existing records loaded    : %s", diagnostics["rolling_delta"]["existing_records_loaded"])
    logger.info("Delta posts                : %s", diagnostics["rolling_delta"]["delta_items"])
    logger.info("Total inserted             : %s", saved_count)
    logger.info("Elapsed time               : %.2f seconds", elapsed_time)
    logger.info("==========================================")
    return {
        "platform": "ptt",
        "status": status,
        "outcome": outcome,
        "technical_success": status in {"success", "partial_success"},
        "data_yield_success": persistence["canonical_posts_written"] > 0 or persistence["canonical_comments_written"] > 0,
        "inserted": saved_count,
        "cards_found": len(posts),
        "comments_found": comments_found,
        "ai_items_enqueued": diagnostics["rolling_delta"]["ai_items_enqueued"],
        "elapsed": elapsed_time,
        "error_type": error_type,
        "error_message": error_message,
        "buffer_path": str(buffer_path) if buffer_path else None,
        **{key: value for key, value in persistence.items() if key.endswith("_written")},
        "persistence": persistence,
        "diagnostics": diagnostics,
    }


def _ptt_effective_post_limit(args) -> int:
    platform_limit = unlimited_or_positive(getattr(args, "platform_max_results", None))
    ptt_limit = unlimited_or_positive(getattr(args, "ptt_max_posts", None), fallback=platform_limit)
    if ptt_limit is None:
        ptt_limit = unlimited_or_positive(getattr(args, "max_results", 50), fallback=50)
    if ptt_limit == 0:
        return 1000
    scroll_limit = unlimited_or_positive(getattr(args, "platform_max_scroll", None))
    page_limit = unlimited_or_positive(getattr(args, "ptt_max_pages", None), fallback=scroll_limit)
    if page_limit is None:
        page_limit = unlimited_or_positive(getattr(args, "max_scroll", 10), fallback=10)
    if page_limit and page_limit > 0:
        return max(1, min(ptt_limit, page_limit * 20))
    return max(1, ptt_limit)


def _ptt_effective_page_limit(args) -> int:
    platform_limit = unlimited_or_positive(getattr(args, "platform_max_scroll", None))
    ptt_limit = unlimited_or_positive(getattr(args, "ptt_max_pages", None), fallback=platform_limit)
    if ptt_limit is None:
        return PTT_INDEX_SCAN_MAX_PAGES
    if ptt_limit == 0:
        return 1000
    return max(1, ptt_limit)


def _set_error(diagnostics: dict, error_type: str, message: str | None, *, recoverable: bool | None) -> None:
    normalized_type = error_type if error_type in PTT_ERROR_TYPES else "unknown"
    diagnostics["error"]["type"] = normalized_type
    diagnostics["error"]["message"] = message
    diagnostics["error"]["recoverable"] = recoverable


def _sync_ptt_diagnostic_aliases(diagnostics: dict) -> None:
    discovery = diagnostics.get("discovery") or {}
    fetch = diagnostics.get("fetch") or {}
    parse = diagnostics.get("parse") or {}
    filters = diagnostics.get("filter") or {}

    discovery["article_urls_discovered"] = int(discovery.get("urls_discovered") or discovery.get("urls_after_dedupe") or 0)
    discovery["article_urls_validated"] = int(discovery.get("urls_after_dedupe") or 0)
    fetch["article_fetch_success"] = int(fetch.get("success") or 0)
    fetch["article_fetch_failed"] = int(fetch.get("failed") or 0)
    parse["articles_parsed"] = int(parse.get("success") or 0)
    filters["keyword_matched"] = int(filters.get("kept_posts") or 0)
    filters["keyword_rejected"] = int(filters.get("dropped_by_relevance") or 0)
    filters["date_rejected"] = int(filters.get("date_rejected") or 0)


def _fetch_error_type(exc: Exception) -> str:
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "timeout"
    if isinstance(exc, aiohttp.ClientResponseError):
        if exc.status in {403, 404, 429}:
            return f"http_{exc.status}"
        return "fetch_failed"
    if isinstance(exc, ConnectionResetError):
        return "connection_reset"
    if isinstance(exc, HTTPError):
        if exc.code == 403:
            return "http_403"
        if exc.code == 404:
            return "http_404"
        if exc.code == 429:
            return "http_429"
        return "fetch_failed"
    if isinstance(exc, URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            return "timeout"
        if isinstance(reason, ConnectionResetError):
            return "connection_reset"
    return "fetch_failed"


def _classify_empty_result(diagnostics: dict) -> tuple[str, str, bool]:
    if diagnostics["fetch"]["attempted"] and diagnostics["fetch"]["success"] == 0:
        error_type = "fetch_zero_yield"
        message = diagnostics["fetch"].get("last_error_message") or "PTT fetch produced no successful article responses."
        return error_type, message, True
    if diagnostics["parse"]["failed"]:
        return "parser_zero_yield", "PTT parser did not produce valid article payloads.", True
    return "empty_result", "PTT crawl returned no posts after discovery, parsing, and filters.", True


def _empty_result_is_technical_failure(error_type: str) -> bool:
    return error_type in {"fetch_zero_yield", "parser_zero_yield"}


def _ptt_status(posts: list[dict], *, buffer_ok: bool, db_error: Exception | None, diagnostics: dict) -> str:
    if posts and diagnostics["error"]["type"] == "buffer_write_failed":
        return "failed"
    if posts and db_error is not None:
        return "partial_success"
    if not posts:
        rolling = diagnostics.get("rolling_delta") or {}
        if rolling.get("items_scanned", 0) > 0 and rolling.get("delta_items", 0) == 0:
            return "success"
        error_type, message, recoverable = _classify_empty_result(diagnostics)
        if _empty_result_is_technical_failure(error_type):
            _set_error(diagnostics, error_type, message, recoverable=recoverable)
            return "failed"
        return "success"
    if posts and buffer_ok:
        return "success"
    _set_error(diagnostics, "unknown", "PTT crawler ended in an unclassified state.", recoverable=True)
    return "failed"


def _ptt_outcome(
    *,
    status: str,
    diagnostics: dict,
    canonical_posts_written: int,
    canonical_comments_written: int,
) -> str:
    if status == "failed":
        return "failed"
    if status == "partial_success":
        return "partial_success"
    if canonical_posts_written > 0 or canonical_comments_written > 0:
        return "success_with_data"
    rolling = diagnostics.get("rolling_delta") or {}
    if rolling.get("items_scanned", 0) > 0:
        return "success_no_changes"
    return "success_no_results"


from adapters.base import CommandModuleCrawler
from adapters.registry import CrawlerRegistry


class PTTCrawler(CommandModuleCrawler):
    def __init__(self) -> None:
        super().__init__("ptt", "adapters.ptt.crawler")


CrawlerRegistry.register("ptt", PTTCrawler)


if __name__ == "__main__":
    asyncio.run(main())
