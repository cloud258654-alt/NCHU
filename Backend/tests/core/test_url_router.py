from core.url_router import URLRouter


def test_url_router_detects_known_platforms():
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

    for url, expected_platform in cases.items():
        assert URLRouter.route(url).platform == expected_platform

