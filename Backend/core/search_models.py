from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


@dataclass(slots=True)
class SearchQuery:
    keyword: str
    engine: str
    site: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    date_range: str = "all"
    max_results: int = 50

    @property
    def rendered_query(self) -> str:
        query = self.keyword.strip()
        if self.site:
            query = f"{query} site:{self.site.strip()}"
        if self.start_date:
            query = f"{query} after:{self.start_date}"
        if self.end_date:
            query = f"{query} before:{self.end_date}"
        return query


def build_search_query(keyword: str, site: str | None = None) -> str:
    return SearchQuery(keyword=keyword, engine="search", site=site).rendered_query


@dataclass(slots=True)
class SearchResult:
    engine: str
    query: str
    url: str
    title: str = ""
    snippet: str = ""
    rank: int = 0
    raw: dict[str, Any] = field(default_factory=dict)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["discovered_at"] = self.discovered_at.isoformat()
        payload["domain"] = self.domain
        return payload

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.lower()


@dataclass(slots=True)
class RoutedSearchResult:
    result: SearchResult
    platform: str
    parser_name: str | None = None

    def as_record(self, *, keyword: str, date_range: str) -> dict[str, Any]:
        return {
            "engine": self.result.engine,
            "keyword": keyword,
            "query": self.result.query,
            "site": None,
            "rank": self.result.rank,
            "url": self.result.url,
            "title": self.result.title,
            "snippet": self.result.snippet,
            "domain": self.result.domain,
            "detected_platform": self.platform,
            "platform": self.platform,
            "parser_name": self.parser_name,
            "date_range": date_range,
            "raw_json": self.result.raw,
            "discovered_at": self.result.discovered_at,
        }
