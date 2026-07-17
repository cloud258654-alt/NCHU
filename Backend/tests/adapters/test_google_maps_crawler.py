import builtins
from pathlib import Path

import pytest

from adapters.google_maps.crawl4ai_snapshot import crawl4ai_page_snapshot
from adapters.google_maps.crawler import (
    _expand_visible_reviews,
    _extract_average_rating,
    _extract_rating_count,
    _is_google_maps_restricted,
    _looks_like_reviews_control,
    _parse_review_card,
    _place_external_id,
    _rating,
    _reviews_url,
    _scroll_reviews,
    _title_from_url,
)


ROOT = Path(__file__).resolve().parents[3]


class FakeElement:
    def __init__(
        self,
        *,
        text="",
        attrs=None,
        children=None,
        visible=True,
    ):
        self.text = text
        self.attrs = attrs or {}
        self.children = children or {}
        self.visible = visible
        self.clicked = 0

    async def inner_text(self, **kwargs):
        return self.text

    async def get_attribute(self, name):
        return self.attrs.get(name)

    async def query_selector(self, selector):
        return self.children.get(selector)

    async def query_selector_all(self, selector):
        return self.children.get(selector, [])

    async def is_visible(self):
        return self.visible

    async def click(self, **kwargs):
        self.clicked += 1


class FakeLocator:
    def __init__(self, text):
        self.text = text

    async def inner_text(self, **kwargs):
        return self.text


class FakePage:
    def __init__(self, body_text="", buttons=None):
        self.body_text = body_text
        self.buttons = buttons or []

    def locator(self, selector):
        assert selector == "body"
        return FakeLocator(self.body_text)

    async def query_selector_all(self, selector):
        assert selector == "button"
        return self.buttons


class FakeMouse:
    def __init__(self):
        self.wheels = []

    async def wheel(self, x, y):
        self.wheels.append((x, y))


class FakeScrollPage:
    def __init__(self):
        self.evaluate_script = ""
        self.evaluate_arg = None
        self.mouse = FakeMouse()

    async def evaluate(self, script, arg):
        self.evaluate_script = script
        self.evaluate_arg = arg
        return True


def test_reviews_url_forces_google_maps_reviews_tab():
    url = "https://www.google.com/maps/place/example/data=!4m7!3m6!1sabc!8m2!3d1!4d2!16s%2Fg%2Fabc"

    assert _reviews_url(url) == (
        "https://www.google.com/maps/place/example/data=!4m7!3m6!1sabc!8m2!3d1!4d2!10e1!16s%2Fg%2Fabc"
    )


def test_reviews_url_keeps_existing_reviews_tab():
    url = "https://www.google.com/maps/place/example/data=!4m7!3m6!1sabc!10e1!16s%2Fg%2Fabc"

    assert _reviews_url(url) == url


def test_reviews_url_does_not_corrupt_modern_direct_place_url():
    url = (
        "https://www.google.com/maps/place/%E8%87%BA%E4%B8%AD%E8%82%89%E5%93%A1/"
        "@24.1345558,120.6829342,18.75z/data=!4m6!3m5!"
        "1s0x34693d05a0945373:0x3514777aba6b24a2!8m2!3d24.134469!"
        "4d120.6825714!16s%2Fg%2F1wtbrmwp?authuser=0&entry=ttu"
    )

    assert _reviews_url(url) == url


def test_place_external_id_extracts_place_id():
    url = "https://www.google.com/maps/place/example/data=!4m7!3m6!1sabc123!8m2!3d1!4d2!16s%2Fg%2Fabc"

    assert _place_external_id(url) == "abc123"


def test_google_maps_summary_parsers_keep_official_rating_separate_from_collected_reviews():
    body = "瓦庫燒肉 4.6 stars (1,234) reviews"

    assert _extract_average_rating(body) == 4.6
    assert _extract_rating_count(body) == 1234


def test_reviews_control_accepts_chinese_and_english_labels():
    assert _looks_like_reviews_control("\u8a55\u8ad6")
    assert _looks_like_reviews_control("Reviews")
    assert not _looks_like_reviews_control("Overview")


def test_title_from_google_maps_place_url():
    url = "https://www.google.com/maps/place/%E6%96%87%E7%AB%A0%E7%89%9B%E8%82%89%E6%B9%AF+%E5%AE%89%E5%B9%B3%E7%B8%BD%E5%BA%97/data=!4m7"

    assert _title_from_url(url) == "\u6587\u7ae0\u725b\u8089\u6e6f \u5b89\u5e73\u7e3d\u5e97"


@pytest.mark.asyncio
async def test_rating_parses_chinese_star_label():
    rating_node = FakeElement(attrs={"aria-label": "5 \u9846\u661f"})
    card = FakeElement(children={"[aria-label]": [rating_node]})

    assert await _rating(card) == 5.0


@pytest.mark.asyncio
async def test_rating_parses_english_star_label():
    rating_node = FakeElement(attrs={"aria-label": "4.5 stars"})
    card = FakeElement(children={"[aria-label]": [rating_node]})

    assert await _rating(card) == 4.5


@pytest.mark.asyncio
async def test_restricted_detection_matches_configured_text():
    page = FakePage(body_text="Our systems have detected unusual traffic from your computer network.")

    assert await _is_google_maps_restricted(page)


@pytest.mark.asyncio
async def test_parse_review_card_uses_class_selector_fields():
    rating_node = FakeElement(attrs={"aria-label": "5 stars"})
    card = FakeElement(
        text="Alice 5 stars 2 days ago Excellent soup",
        attrs={"data-review-id": "review-1"},
        children={
            ".d4r55, [class*='fontHeadlineSmall']": FakeElement(text="Alice"),
            ".wiI7pd, [class*='MyEned']": FakeElement(text="Excellent soup"),
            ".rsqaWe, [class*='rsqaWe']": FakeElement(text="2 days ago"),
            "[aria-label]": [rating_node],
        },
    )

    review = await _parse_review_card(card, place_url="https://maps.example/place", keyword="missing")

    assert review["id"] == "review-1"
    assert review["author_name"] == "Alice"
    assert review["content"] == "Excellent soup"
    assert review["rating"] == 5.0
    assert review["comment_time_raw"] == "2 days ago"
    assert review["raw_json"]["parser_strategy"] == "class_selector"


@pytest.mark.asyncio
async def test_parse_review_card_falls_back_to_full_card_text():
    card = FakeElement(
        text="Bob\n3 weeks ago\nWorth a visit\nMore",
        attrs={"data-review-id": "review-2"},
        children={
            "[aria-label]": [],
        },
    )

    review = await _parse_review_card(card, place_url="https://maps.example/place", keyword="")

    assert review["author_name"] == "Bob"
    assert review["content"] == "Worth a visit"
    assert review["comment_time_raw"] == "3 weeks ago"
    assert review["raw_json"]["full_card_text"] == "Bob 3 weeks ago Worth a visit More"
    assert review["raw_json"]["parser_strategy"] == "fallback_text"


@pytest.mark.asyncio
async def test_expand_visible_reviews_returns_clicked_count():
    more = FakeElement(text="More")
    hidden = FakeElement(text="More", visible=False)
    other = FakeElement(text="Share")
    page = FakePage(buttons=[more, hidden, other])

    diagnostics = {"reviews": {"expanded_buttons_clicked": 0}}
    clicked = await _expand_visible_reviews(page, diagnostics=diagnostics)

    assert clicked == 1
    assert more.clicked == 1
    assert hidden.clicked == 0
    assert diagnostics["reviews"]["expanded_buttons_clicked"] == 1


@pytest.mark.asyncio
async def test_scroll_reviews_anchors_on_last_review_card():
    page = FakeScrollPage()
    diagnostics = {"reviews": {"scroll_rounds": 0}}

    await _scroll_reviews(page, diagnostics=diagnostics)

    assert "lastReviewCard.scrollIntoView" in page.evaluate_script
    assert "scroller.dispatchEvent" in page.evaluate_script
    assert diagnostics["reviews"]["scroll_rounds"] == 1
    assert page.mouse.wheels


def test_no_new_platform_specific_official_tables_are_introduced():
    sql = (ROOT / "database" / "schema.sql").read_text(encoding="utf-8")

    forbidden_tables = (
        "CREATE TABLE google_maps_posts",
        "CREATE TABLE google_maps_reviews",
        "CREATE TABLE web_pages",
    )
    for table in forbidden_tables:
        assert table not in sql


@pytest.mark.asyncio
async def test_crawl4ai_snapshot_missing_package_is_graceful(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "crawl4ai":
            raise ModuleNotFoundError("No module named 'crawl4ai'")
        return real_import(name, *args, **kwargs)

    diagnostics = {"crawl4ai": {"attempted": False, "success": False, "error": None}}
    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = await crawl4ai_page_snapshot("https://example.com", diagnostics=diagnostics)

    assert result == {
        "success": False,
        "error": "crawl4ai_not_installed",
        "markdown": "",
        "metadata": {},
    }
    assert diagnostics["crawl4ai"]["attempted"] is True
    assert diagnostics["crawl4ai"]["error"] == "crawl4ai_not_installed"


def test_crawl4ai_snapshot_has_no_remote_extraction_terms():
    source = (ROOT / "Backend/adapters/google_maps/crawl4ai_snapshot.py").read_text(encoding="utf-8")

    forbidden = (
        "LLMExtractionStrategy",
        "OpenAI",
        "Gemini",
        "Claude",
        "provider",
        "api_key",
        "model",
    )
    for term in forbidden:
        assert term not in source


def test_crawler_has_no_disallowed_browser_stack_terms():
    source = (ROOT / "Backend/adapters/google_maps/crawler.py").read_text(encoding="utf-8").lower()

    forbidden = (
        "undetected_chromedriver",
        "selenium",
        "stealth",
        "proxy",
        "captcha bypass",
    )
    for term in forbidden:
        assert term not in source
