from adapters.registry import CrawlerRegistry, load_builtin_crawlers
from core.url_router import URLRouter


def test_registry_loads_builtin_platforms():
    load_builtin_crawlers()

    platforms = set(CrawlerRegistry.available())

    assert platforms >= {"google_maps", "ptt", "threads", "web"}
    assert "web" in platforms


def test_search_url_router_detects_platforms():
    cases = {
        "https://www.threads.com/@brand/post/abc": "threads",
        "https://www.threads.net/@brand/post/abc": "threads",
        "https://www.ptt.cc/bbs/Food/M.123.html": "ptt",
        "https://www.google.com/maps/place/example": "google_maps",
        "https://www.youtube.com/watch?v=abc": "web",
        "https://www.instagram.com/p/abc/": "web",
        "https://www.dcard.tw/f/food/p/123": "web",
        "https://example.com/article": "web",
    }

    for url, platform in cases.items():
        assert URLRouter.route(url).platform == platform

