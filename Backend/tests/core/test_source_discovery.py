import asyncio
import base64
import time

import pytest

import core.source_discovery as source_discovery
from core.search_config import SearchConfig
from core.search_models import SearchResult


class FakeEngine:
    def __init__(self, name, results=None, exc=None, captured_configs=None, config=None):
        self.name = name
        self.results = results or []
        self.exc = exc
        self.captured_configs = captured_configs
        if captured_configs is not None:
            captured_configs.append((name, config))

    async def search(self, query):
        if self.exc:
            raise self.exc
        return [
            SearchResult(
                engine=self.name,
                query=query.rendered_query,
                url=result.url,
                title=result.title,
                rank=index + 1,
            )
            for index, result in enumerate(self.results)
        ]


def test_google_maps_discovery_queries_ignore_optional_keyword(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_DISCOVERY_QUERY_VARIANT_LIMIT", "4")

    queries = source_discovery.build_google_maps_discovery_queries(
        "Example Store",
        "ramen",
        location="Taipei",
    )

    assert queries == [
        "Example Store Taipei site:google.com/maps",
        "Example Store Taipei Google Maps",
    ]
    assert all("ramen" not in query for query in queries)


def test_google_maps_engine_auto_order(monkeypatch):
    monkeypatch.setattr(source_discovery, "load_config", lambda: SearchConfig(searxng_base_url="http://localhost:8080"))

    assert source_discovery.google_maps_discovery_engine_names("auto") == ["searxng", "duckduckgo", "bing"]
    assert source_discovery.google_maps_discovery_engine_names("auto", searxng_base_url=None) == ["duckduckgo", "bing"]
    assert source_discovery.google_maps_discovery_engine_names("disabled") == []
    assert source_discovery.google_maps_discovery_engine_names("bing") == ["bing"]


def test_google_maps_url_classification_and_normalization():
    assert source_discovery.classify_google_maps_candidate("") == ("", "empty_url")
    assert source_discovery.classify_google_maps_candidate("https://www.google.com/") == ("", "google_homepage")
    assert source_discovery.classify_google_maps_candidate("https://www.google.com/maps") == ("", "maps_homepage")
    assert source_discovery.classify_google_maps_candidate("https://example.com/maps/place/a") == ("", "unsupported_domain")
    assert source_discovery.classify_google_maps_candidate("https://www.google.com/search?q=maps") == ("", "google_homepage")

    assert source_discovery.classify_google_maps_candidate(
        "https://www.google.com/maps/place/Example?entry=ttu&g_st=ic"
    ) == ("https://www.google.com/maps/place/Example", "accepted")
    assert source_discovery.classify_google_maps_candidate(
        "https://maps.google.com/?cid=123&utm_source=x"
    ) == ("https://www.google.com/maps?cid=123", "accepted")
    assert source_discovery.classify_google_maps_candidate(
        "https://www.google.com/maps/search/?api=1&query=Example&tracking=1"
    ) == ("https://www.google.com/maps/search/?api=1&query=Example", "accepted")
    assert source_discovery.classify_google_maps_candidate(
        "https://www.google.com/maps?place_id=abc&entry=ttu"
    ) == ("https://www.google.com/maps?place_id=abc", "accepted")
    assert source_discovery.classify_google_maps_candidate(
        "https://www.google.com/maps?query_place_id=abc&entry=ttu"
    ) == ("https://www.google.com/maps?query_place_id=abc", "accepted")
    assert source_discovery.classify_google_maps_candidate(
        "https://www.google.com.tw/maps/place/Example?entry=ttu"
    ) == ("https://www.google.com/maps/place/Example", "accepted")
    assert source_discovery.classify_google_maps_candidate(
        "https://maps.google.com.tw/?cid=123&utm_source=x"
    ) == ("https://www.google.com/maps?cid=123", "accepted")
    assert source_discovery.classify_google_maps_candidate("https://maps.app.goo.gl/abc123") == (
        "",
        "short_redirect_unresolved",
    )

    candidate = source_discovery.google_maps_candidate_from_result(
        SearchResult(
            engine="duckduckgo",
            query="Example Store",
            url="https://www.google.com/maps?query_place_id=abc&entry=ttu",
            title="Example Store",
            rank=1,
        ),
        business_name="Example Store",
        location=None,
        seen=set(),
    )
    assert candidate.accepted is True
    assert candidate.candidate_type == "place_id_url"


def test_google_maps_candidate_rejects_wrong_business():
    candidate = source_discovery.google_maps_candidate_from_result(
        SearchResult(
            engine="duckduckgo",
            query="Example Store",
            url="https://www.google.com/maps/place/Another+Store",
            title="Another Store",
            rank=1,
        ),
        business_name="Example Store",
        location=None,
        seen=set(),
    )

    assert candidate.accepted is False
    assert candidate.rejection_reason == "business_mismatch"


@pytest.mark.asyncio
async def test_discover_google_maps_prefers_scored_place_url(monkeypatch):
    search_url = "https://www.google.com/maps/search/?api=1&query=Example"
    place_url = "https://www.google.com/maps/place/Example+Store/data=!4m6"

    class Result:
        def __init__(self, url, title):
            self.url = url
            self.title = title

    monkeypatch.setattr(source_discovery, "load_config", lambda: SearchConfig(searxng_base_url=None))
    monkeypatch.setattr(
        source_discovery,
        "create_engine",
        lambda name, config: FakeEngine(
            name,
            results=[
                Result("https://example.com/not-maps", "Article"),
                Result(search_url, "Example Store - Google Maps"),
                Result(place_url, "Example Store"),
                Result(place_url, "Example Store duplicate"),
            ],
        ),
    )

    result = await source_discovery.discover_google_maps_source_url(
        business_name="Example Store",
        keyword="ramen",
    )

    assert result.url == place_url
    assert result.source == "duckduckgo"
    assert result.diagnostics["engines_attempted"] == ["duckduckgo"]
    assert result.diagnostics["accepted_candidates"] == 2
    assert result.diagnostics["rejected_candidates"] >= 2
    reasons = [item["rejection_reason"] for item in result.diagnostics["results"]]
    assert "unsupported_domain" in reasons
    assert "duplicate" in reasons
    assert all("snippet" not in item for item in result.diagnostics["results"])


@pytest.mark.asyncio
async def test_discover_google_maps_falls_back_across_engines(monkeypatch):
    class Result:
        def __init__(self, url, title):
            self.url = url
            self.title = title

    def fake_create_engine(name, config):
        if name == "searxng":
            return FakeEngine(name, exc=RuntimeError("searxng offline"))
        if name == "duckduckgo":
            return FakeEngine(name, results=[Result("https://example.com", "not maps")])
        return FakeEngine(name, results=[Result("https://www.google.com/maps?cid=123", "Example Store")])

    monkeypatch.setattr(source_discovery, "load_config", lambda: SearchConfig(searxng_base_url="http://localhost:8080"))
    monkeypatch.setattr(source_discovery, "create_engine", fake_create_engine)

    result = await source_discovery.discover_google_maps_source_url(business_name="Example Store")

    assert result.url == "https://www.google.com/maps?cid=123"
    assert result.source == "bing"
    assert result.diagnostics["engines_attempted"] == ["searxng", "duckduckgo", "bing"]
    assert result.diagnostics["errors"][0]["engine"] == "searxng"


@pytest.mark.asyncio
async def test_discover_google_maps_continues_after_low_confidence_search_candidate(monkeypatch):
    class Result:
        def __init__(self, url, title):
            self.url = url
            self.title = title

    def fake_create_engine(name, config):
        if name == "duckduckgo":
            return FakeEngine(
                name,
                results=[Result("https://www.google.com/maps/search/?api=1&query=Example", "Example Store")],
            )
        return FakeEngine(
            name,
            results=[Result("https://www.google.com/maps/place/Example+Store", "Example Store - Google Maps")],
        )

    monkeypatch.setattr(source_discovery, "load_config", lambda: SearchConfig(searxng_base_url=None))
    monkeypatch.setattr(source_discovery, "create_engine", fake_create_engine)

    result = await source_discovery.discover_google_maps_source_url(business_name="Example Store")

    assert result.url == "https://www.google.com/maps/place/Example+Store"
    assert result.source == "bing"
    assert result.diagnostics["engines_attempted"] == ["duckduckgo", "bing"]
    selected = [
        item
        for item in result.diagnostics["results"]
        if item["normalized_url"] == "https://www.google.com/maps/place/Example+Store"
    ][0]
    assert selected["candidate_type"] == "place_url"


@pytest.mark.asyncio
async def test_discover_google_maps_continues_after_maps_home_candidate(monkeypatch):
    class Result:
        def __init__(self, url, title):
            self.url = url
            self.title = title

    def fake_create_engine(name, config):
        if name == "searxng":
            return FakeEngine(name, results=[Result("https://www.google.com/maps?query=Example", "Google Maps")])
        return FakeEngine(name, results=[Result("https://www.google.com/maps?cid=123", "Example Store")])

    monkeypatch.setattr(source_discovery, "load_config", lambda: SearchConfig(searxng_base_url="http://localhost:8080"))
    monkeypatch.setattr(source_discovery, "create_engine", fake_create_engine)

    result = await source_discovery.discover_google_maps_source_url(business_name="Example Store")

    assert result.url == "https://www.google.com/maps?cid=123"
    assert result.source == "duckduckgo"
    assert result.diagnostics["engines_attempted"] == ["searxng", "duckduckgo"]
    candidate_types = [item["candidate_type"] for item in result.diagnostics["results"] if item["accepted"]]
    assert candidate_types == ["cid_url"]
    rejected = [item for item in result.diagnostics["results"] if not item["accepted"]]
    assert any(item["rejection_reason"] == "business_mismatch" for item in rejected)


@pytest.mark.asyncio
async def test_discover_google_maps_generated_fallback_when_disabled(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_DISCOVERY_ENABLED", "disabled")
    diagnostics = {}

    result = await source_discovery.discover_google_maps_source_url(
        business_name="Example Store",
        location="Taipei",
        diagnostics=diagnostics,
    )

    assert result.url == "https://www.google.com/maps/search/Example+Store+Taipei"
    assert result.source == "generated_fallback"
    assert result.diagnostics["fallback_used"] is True
    assert result.diagnostics["engines_attempted"] == []
    assert diagnostics["selected_source"] == "generated_fallback"


@pytest.mark.asyncio
async def test_discovery_deadline_limits_retry_config(monkeypatch):
    captured = []

    class Result:
        def __init__(self, url, title):
            self.url = url
            self.title = title

    monkeypatch.setattr(source_discovery, "load_config", lambda: SearchConfig(timeout_seconds=20.0, retry_attempts=3))
    monkeypatch.setattr(
        source_discovery,
        "create_engine",
        lambda name, config: FakeEngine(
            name,
            config=config,
            captured_configs=captured,
            results=[Result("https://www.google.com/maps/place/Example", "Example Store")],
        ),
    )

    result = await source_discovery.discover_google_maps_source_url(
        business_name="Example Store",
        deadline=time.monotonic() + 0.5,
    )

    assert result.url == "https://www.google.com/maps/place/Example"
    assert captured
    assert all(config.retry_attempts == 1 for _name, config in captured)
    assert all(0 < config.timeout_seconds <= 0.5 for _name, config in captured)


@pytest.mark.asyncio
async def test_discovery_deadline_expired_still_returns_generated_fallback(monkeypatch):
    def fail_create_engine(name, config):
        raise AssertionError("engine should not be created after deadline")

    monkeypatch.setattr(source_discovery, "create_engine", fail_create_engine)

    result = await source_discovery.discover_google_maps_source_url(
        business_name="Example Store",
        deadline=time.monotonic() - 1,
    )

    assert result.url == "https://www.google.com/maps/search/Example+Store"
    assert result.source == "generated_fallback"
    assert result.diagnostics["fallback_used"] is True
    assert result.diagnostics["errors"][0]["type"] == "timeout"


def test_bing_redirect_is_decoded_for_google_maps_candidate():
    target = "https://www.google.com/maps/place/Example"
    encoded = "a1" + base64.urlsafe_b64encode(target.encode("utf-8")).decode("ascii").rstrip("=")

    assert source_discovery.classify_google_maps_candidate(f"https://www.bing.com/ck/a?u={encoded}") == (
        target,
        "accepted",
    )


def test_discover_platform_urls_skips_when_google_maps_not_selected(monkeypatch):
    def fail_discover(*args, **kwargs):
        raise AssertionError("Google Maps discovery should not run")

    monkeypatch.setattr(source_discovery, "discover_google_maps_source_url", fail_discover)

    urls = asyncio.run(
        source_discovery.discover_platform_urls(
            business_name="Example Store",
            platforms=["threads"],
        )
    )

    assert urls == {}
