from __future__ import annotations

import json
import base64
from abc import ABC, abstractmethod
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

import random
import time
from urllib.error import HTTPError, URLError

from core.logger import get_logger
from core.search_config import SearchConfig
from core.search_models import SearchQuery, SearchResult

logger = get_logger("core.search_engines")

class SearchEngine(ABC):
    name: str

    def __init__(self, config: SearchConfig) -> None:
        self.config = config

    @abstractmethod
    async def search(self, query: SearchQuery) -> list[SearchResult]:
        raise NotImplementedError

    def _fetch_text(self, url: str, params: dict[str, str]) -> str:
        target = f"{url}?{urlencode(params)}"
        last_error: Exception | None = None
        RETRYABLE_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}
        NON_RETRYABLE_HTTP_STATUS = {400, 401, 403, 404, 410}

        for attempt in range(self.config.retry_attempts):
            try:
                request = Request(target, headers={"User-Agent": self.config.user_agent})
                with urlopen(request, timeout=self.config.timeout_seconds) as response:
                    charset = response.headers.get_content_charset() or "utf-8"
                    return response.read().decode(charset, errors="replace")
            except HTTPError as exc:
                if exc.code in NON_RETRYABLE_HTTP_STATUS:
                    logger.warning(
                        "Search fetch non-retryable HTTP error: url=%s status=%s params=%s",
                        url,
                        exc.code,
                        params,
                    )
                    raise
                if exc.code not in RETRYABLE_HTTP_STATUS:
                    logger.warning(
                        "Search fetch unexpected HTTP error: url=%s status=%s params=%s",
                        url,
                        exc.code,
                        params,
                    )
                    raise
                last_error = exc
            except (TimeoutError, ConnectionResetError, URLError) as exc:
                last_error = exc

            if attempt >= self.config.retry_attempts - 1:
                break

            delay = min(
                self.config.retry_max_delay,
                self.config.retry_base_delay * (2 ** attempt),
            ) + random.uniform(0.2, 1.2)

            logger.warning(
                "Search fetch retry: url=%s params=%s attempt=%s/%s delay=%.2fs error=%s",
                url,
                params,
                attempt + 1,
                self.config.retry_attempts,
                delay,
                last_error,
            )
            time.sleep(delay)

        raise last_error or RuntimeError("Search fetch failed without explicit exception")


class DuckDuckGoEngine(SearchEngine):
    name = "duckduckgo"

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        html = self._fetch_text("https://duckduckgo.com/html/", {"q": query.rendered_query})
        parser = DuckDuckGoHTMLParser(self.name, query)
        parser.feed(html)
        results = parser.results[: query.max_results]
        logger.info("Search engine completed: engine=%s query=%s result_count=%s", self.name, query.rendered_query, len(results))
        return results


class BingEngine(SearchEngine):
    name = "bing"

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        html = self._fetch_text("https://www.bing.com/search", {"q": query.rendered_query})
        parser = BingHTMLParser(self.name, query)
        parser.feed(html)
        results = parser.results[: query.max_results]
        logger.info("Search engine completed: engine=%s query=%s result_count=%s", self.name, query.rendered_query, len(results))
        return results


class SearXNGEngine(SearchEngine):
    name = "searxng"

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        if not self.config.searxng_base_url:
            raise ValueError("SEARXNG_BASE_URL is required for engine=searxng")

        text = self._fetch_text(
            f"{self.config.searxng_base_url.rstrip('/')}/search",
            {"q": query.rendered_query, "format": "json"},
        )
        payload = json.loads(text)
        results: list[SearchResult] = []
        for item in payload.get("results", []):
            url = item.get("url")
            if not url:
                continue
            results.append(
                SearchResult(
                    engine=self.name,
                    query=query.rendered_query,
                    url=url,
                    title=item.get("title") or "",
                    snippet=item.get("content") or "",
                    rank=len(results) + 1,
                    raw=item,
                )
            )
            if len(results) >= query.max_results:
                break
        logger.info("Search engine completed: engine=%s query=%s result_count=%s", self.name, query.rendered_query, len(results))
        return results


class GoogleSearchEngine(SearchEngine):
    name = "google"

    async def search(self, query: SearchQuery) -> list[SearchResult]:
        raise NotImplementedError(
            "Google Search scraping is intentionally not implemented. "
            "Use duckduckgo, bing, searxng, or provide an API-backed implementation."
        )


class DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self, engine: str, query: SearchQuery) -> None:
        super().__init__(convert_charrefs=True)
        self.engine = engine
        self.query = query
        self.results: list[SearchResult] = []
        self._capture_title = False
        self._capture_snippet = False
        self._current_url = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = attr.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._capture_title = True
            self._current_url = _clean_duckduckgo_url(attr.get("href") or "")
            self._title_parts = []
            self._snippet_parts = []
        elif self._current_url and "result__snippet" in classes:
            self._capture_snippet = True

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)
        elif self._capture_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
        elif self._capture_snippet and tag in {"a", "div"}:
            self._capture_snippet = False
            self._append_current()

    def close(self) -> None:
        self._append_current()
        super().close()

    def _append_current(self) -> None:
        if not self._current_url:
            return
        self.results.append(
            SearchResult(
                engine=self.engine,
                query=self.query.rendered_query,
                url=self._current_url,
                title=_clean_text(" ".join(self._title_parts)),
                snippet=_clean_text(" ".join(self._snippet_parts)),
                rank=len(self.results) + 1,
                raw={"source": "duckduckgo_html"},
            )
        )
        self._current_url = ""


class BingHTMLParser(HTMLParser):
    def __init__(self, engine: str, query: SearchQuery) -> None:
        super().__init__(convert_charrefs=True)
        self.engine = engine
        self.query = query
        self.results: list[SearchResult] = []
        self._in_h2 = False
        self._capture_title = False
        self._current_url = ""
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "h2":
            self._in_h2 = True
        elif self._in_h2 and tag == "a":
            self._current_url = attr.get("href") or ""
            self._title_parts = []
            self._capture_title = bool(self._current_url)

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title:
            self._capture_title = False
            self._append_current()
        elif tag == "h2":
            self._in_h2 = False

    def _append_current(self) -> None:
        if not self._current_url:
            return
        self.results.append(
            SearchResult(
                engine=self.engine,
                query=self.query.rendered_query,
                url=_clean_bing_url(self._current_url),
                title=_clean_text(" ".join(self._title_parts)),
                rank=len(self.results) + 1,
                raw={"source": "bing_html"},
            )
        )
        self._current_url = ""


def create_engine(name: str, config: SearchConfig) -> SearchEngine:
    engines: dict[str, type[SearchEngine]] = {
        "duckduckgo": DuckDuckGoEngine,
        "bing": BingEngine,
        "searxng": SearXNGEngine,
        "google": GoogleSearchEngine,
    }
    try:
        return engines[name](config)
    except KeyError as exc:
        available = ", ".join(sorted(engines))
        raise ValueError(f"Unsupported search engine '{name}'. Available: {available}") from exc


def engine_names_for(option: str, config: SearchConfig) -> list[str]:
    if option == "auto":
        names = []
        if config.searxng_base_url:
            names.append("searxng")
        names.extend(["duckduckgo", "bing"])
        return names
    if option == "all":
        names = []
        if config.searxng_base_url:
            names.append("searxng")
        names.extend(["duckduckgo", "bing"])
        return names
    return [option]


def _clean_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    if url.startswith("//duckduckgo.com/l/"):
        parsed = urlparse(f"https:{url}")
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target)
    return url


def _clean_bing_url(url: str) -> str:
    parsed = urlparse(url)
    if "bing.com" not in parsed.netloc or not parsed.path.startswith("/ck/"):
        return url
    encoded = parse_qs(parsed.query).get("u", [""])[0]
    if not encoded:
        return url
    if encoded.startswith("a1"):
        encoded = encoded[2:]
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(f"{encoded}{padding}").decode("utf-8")
    except Exception:
        return url


def _clean_text(value: str) -> str:
    return " ".join(unescape(value).split())
