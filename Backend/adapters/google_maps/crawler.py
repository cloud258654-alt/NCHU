from __future__ import annotations

import argparse
import asyncio
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import core.cli as cli
import core.logger as logger_mod
import core.runtime_settings as runtime_settings
import core.supabase as db
from adapters.google_maps.delta import classify_google_reviews, normalize_place_url

logger = logger_mod.get_logger("adapters.google_maps")

PLACE_CARD_SELECTOR = 'div.Nv2PK, div[role="article"]'
REVIEW_CARD_SELECTOR = "div[data-review-id], div.jftiEf"
REVIEWS_TOKENS = ("\u8a55\u8ad6", "Reviews", "reviews")
MORE_TOKENS = ("\u66f4\u591a", "\u5168\u6587", "More", "more")
RESTRICTED_TEXT = "\u76ee\u524d\u770b\u5230\u7684 Google \u5730\u5716\u5167\u5bb9\u53d7\u9650"
RESTRICTED_TEXT_TOKENS = (
    RESTRICTED_TEXT,
    "Google Maps content is limited",
    "Our systems have detected unusual traffic",
    "unusual traffic",
    "captcha",
    "Captcha",
)


async def scrape_google_maps(
    url: str,
    keyword: str,
    *,
    max_scroll: int,
    max_minutes: float,
    headless: bool,
    runtime_diagnostics: dict | None = None,
) -> list[dict]:
    """Scrape Google Maps place reviews.

    Output shape: one crawl_posts row per place, individual reviews under
    `reviews` so the persistence layer writes them into comments.
    """

    from playwright.async_api import async_playwright

    started = time.monotonic()
    places: list[dict] = []
    if runtime_diagnostics is not None:
        runtime_diagnostics["deadline_reached"] = False
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=["--lang=zh-TW"])
        context = await browser.new_context(**_context_options())
        page = await context.new_page()

        try:
            if _timed_out(started, max_minutes):
                return places
            await page.goto(url, wait_until="domcontentloaded", timeout=_timeout_ms(started, max_minutes, 60000))
            await _wait_for_remaining(page, started=started, max_minutes=max_minutes, milliseconds=3000)
            place_urls = await _discover_place_urls(page, fallback_url=url)
            logger.info("Google Maps place URLs discovered: %s", len(place_urls))

            for place_url in place_urls:
                if _timed_out(started, max_minutes):
                    break
                place = await _scrape_place_reviews(
                    page,
                    place_url=place_url,
                    source_url=url,
                    keyword=keyword,
                    max_scroll=max_scroll,
                    max_minutes=max_minutes,
                    started=started,
                )
                if place:
                    places.append(place)
        except Exception as exc:
            if _timed_out(started, max_minutes):
                logger.warning("Google Maps crawl stopped at its soft deadline: %s", exc)
            else:
                raise
        finally:
            if runtime_diagnostics is not None:
                runtime_diagnostics["deadline_reached"] = _timed_out(started, max_minutes)
            await browser.close()
    return places


def _rolling_window(*, lookback_days: int | None) -> tuple[datetime, datetime]:
    if lookback_days is not None and lookback_days < 0:
        raise ValueError("lookback_days must be >= 0")
    triggered_at = datetime.now(timezone.utc)
    window_start = (
        datetime(1970, 1, 1, tzinfo=timezone.utc)
        if lookback_days in (None, 0)
        else triggered_at - timedelta(days=lookback_days)
    )
    return window_start, triggered_at


def _context_options() -> dict:
    options = {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "locale": "zh-TW",
        "viewport": {"width": 1280, "height": 900},
    }
    storage_state = Path(runtime_settings.STORAGE_STATE_PATH)
    if storage_state.exists():
        options["storage_state"] = str(storage_state)
        logger.info("Google Maps using Playwright storage_state: %s", storage_state)
    return options


async def _discover_place_urls(page, *, fallback_url: str) -> list[str]:
    cards = await page.query_selector_all(PLACE_CARD_SELECTOR)
    urls: list[str] = []
    seen: set[str] = set()
    for card in cards:
        place_url = await _card_url(card)
        if not place_url or place_url in seen:
            continue
        seen.add(place_url)
        urls.append(place_url)
    return urls or [fallback_url]


async def _scrape_place_reviews(
    page,
    *,
    place_url: str,
    source_url: str,
    keyword: str,
    max_scroll: int,
    max_minutes: float,
    started: float,
) -> dict:
    if _timed_out(started, max_minutes):
        return {}
    await page.goto(_reviews_url(place_url), wait_until="domcontentloaded", timeout=_timeout_ms(started, max_minutes, 60000))
    await _wait_for_remaining(page, started=started, max_minutes=max_minutes, milliseconds=4000)
    await _open_reviews_tab(page, started=started, max_minutes=max_minutes)
    if await _is_google_maps_restricted(page):
        logger.warning("Google Maps reviews are restricted for this session: %s", place_url)
        return {}

    await _load_reviews(page, max_scroll=max_scroll, max_minutes=max_minutes, started=started)

    title = await _place_title(page) or _title_from_url(place_url)
    summary = await _place_rating_summary(page)
    reviews = await _parse_reviews(page, place_url=place_url, keyword="")
    if not reviews:
        logger.warning("Google Maps place loaded but no review cards were parsed: %s", place_url)
        return {}

    normalized_place_url = normalize_place_url(place_url)
    return {
        "post_url": normalized_place_url,
        "external_id": _place_external_id(place_url),
        "title": f"Google Maps reviews: {title or place_url}",
        "author_name": title,
        "content": f"{title or 'Google Maps place'} reviews",
        "comment_count": len(reviews),
        "reaction_count": len(reviews),
        "average_rating": summary.get("average_rating"),
        "rating_count": summary.get("rating_count"),
        "keyword": keyword,
        "source": "google_maps",
        "reviews": reviews,
        "raw_json": {
            "source_url": source_url,
            "place_url": normalized_place_url,
            "average_rating": summary.get("average_rating"),
            "rating_count": summary.get("rating_count"),
            "review_count": len(reviews),
        },
    }


async def _open_reviews_tab(page, *, started: float, max_minutes: float) -> None:
    try:
        tabs = page.locator('[role="tab"]')
        for index in range(await tabs.count()):
            if _timed_out(started, max_minutes):
                return
            tab = tabs.nth(index)
            label = f"{await tab.inner_text(timeout=_timeout_ms(started, max_minutes, 1000))} {await tab.get_attribute('aria-label') or ''}"
            if _looks_like_reviews_control(label):
                await tab.click()
                await _wait_for_remaining(page, started=started, max_minutes=max_minutes, milliseconds=2500)
                return
    except Exception:
        pass

    for selector in (
        'button[aria-label*="\u8a55\u8ad6"]',
        'button[aria-label*="Reviews"]',
        'button[jsaction*="pane.rating.moreReviews"]',
    ):
        try:
            if _timed_out(started, max_minutes):
                return
            button = page.locator(selector)
            if await button.count() > 0:
                await button.first.click()
                await _wait_for_remaining(page, started=started, max_minutes=max_minutes, milliseconds=2500)
                return
        except Exception:
            continue


async def _load_reviews(page, *, max_scroll: int, max_minutes: float, started: float) -> None:
    stable_rounds = 0
    previous_count = -1
    for _ in range(max_scroll):
        if _timed_out(started, max_minutes):
            break
        await _expand_visible_reviews(page)
        current_count = await _review_count(page)
        stable_rounds = stable_rounds + 1 if current_count <= previous_count else 0
        previous_count = current_count
        if stable_rounds >= 2:
            break
        await _scroll_reviews(page)
        await _wait_for_remaining(page, started=started, max_minutes=max_minutes, milliseconds=1200)
    await _expand_visible_reviews(page)


async def _review_count(page) -> int:
    return await page.locator(REVIEW_CARD_SELECTOR).count()


async def _place_rating_summary(page) -> dict[str, float | int | None]:
    text = " ".join((await page.locator("body").inner_text()).split())
    return {
        "average_rating": _extract_average_rating(text),
        "rating_count": _extract_rating_count(text),
    }


def _extract_average_rating(text: str) -> float | None:
    match = re.search(r"\b([1-5](?:[.,]\d)?)\s*(?:顆星|星|stars?)\b", text, re.IGNORECASE)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    return round(value, 2) if 1 <= value <= 5 else None


def _extract_rating_count(text: str) -> int | None:
    for pattern in (r"([\d,]+)\s*(?:則)?(?:評論|reviews?)", r"\(([\d,]+)\)"):
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            continue
    return None


async def _scroll_reviews(page, diagnostics: dict | None = None) -> None:
    try:
        await page.evaluate(
            """
            () => {
              const candidates = Array.from(document.querySelectorAll('div'))
                .filter(el => el.scrollHeight > el.clientHeight + 100)
                .map(el => ({
                  el,
                  reviews: el.querySelectorAll('[data-review-id], .jftiEf').length,
                  overflow: el.scrollHeight - el.clientHeight
                }))
                .filter(item => item.reviews > 0)
                .sort((a, b) => (b.reviews - a.reviews) || (b.overflow - a.overflow));
              const scroller = candidates[0]?.el;
              const reviewCards = document.querySelectorAll('[data-review-id], .jftiEf');
              const lastReviewCard = reviewCards[reviewCards.length - 1];
              if (lastReviewCard) lastReviewCard.scrollIntoView({ block: 'end' });
              if (scroller) {
                scroller.scrollTop = Math.min(scroller.scrollHeight, scroller.scrollTop + scroller.clientHeight * 2);
                scroller.dispatchEvent(new Event('scroll', { bubbles: true }));
              }
              else window.scrollTo(0, document.body.scrollHeight);
            }
            """,
            None,
        )
    except Exception:
        await page.mouse.wheel(0, 1600)
    else:
        await page.mouse.wheel(0, 1600)
    if diagnostics is not None:
        reviews = diagnostics.setdefault("reviews", {})
        reviews["scroll_rounds"] = int(reviews.get("scroll_rounds") or 0) + 1


async def _expand_visible_reviews(page, diagnostics: dict | None = None) -> int:
    clicked = 0
    buttons = await page.query_selector_all("button")
    for button in buttons[:120]:
        try:
            if hasattr(button, "is_visible") and not await button.is_visible():
                continue
            label = " ".join((await button.inner_text()).split())
            aria = await button.get_attribute("aria-label") or ""
            if any(token in f"{label} {aria}" for token in MORE_TOKENS):
                await button.click(timeout=1000)
                clicked += 1
        except Exception:
            continue
    if diagnostics is not None:
        reviews = diagnostics.setdefault("reviews", {})
        reviews["expanded_buttons_clicked"] = int(reviews.get("expanded_buttons_clicked") or 0) + clicked
    return clicked


async def _parse_reviews(page, *, place_url: str, keyword: str) -> list[dict]:
    reviews: list[dict] = []
    seen: set[str] = set()
    cards = await page.query_selector_all(REVIEW_CARD_SELECTOR)
    for card in cards:
        review = await _parse_review_card(card, place_url=place_url, keyword=keyword)
        if not review:
            continue
        dedupe = review.get("id") or "|".join(
            [
                review.get("author_name", ""),
                review.get("comment_time_raw", ""),
                review.get("content", "")[:120],
            ]
        )
        if dedupe in seen:
            continue
        seen.add(dedupe)
        reviews.append(review)
    return reviews


async def _parse_review_card(card, *, place_url: str, keyword: str) -> dict | None:
    text = " ".join((await card.inner_text()).split())
    if not text:
        return None
    author = await _text(card, ".d4r55, [class*='fontHeadlineSmall']")
    content = await _text(card, ".wiI7pd, [class*='MyEned']") or text
    parser_strategy = "class_selector" if author and content != text else "fallback_text"
    relative_time = await _text(card, ".rsqaWe, [class*='rsqaWe']")
    if parser_strategy == "fallback_text":
        author, relative_time, content = _parse_review_fallback_text(text)
    review_id = await card.get_attribute("data-review-id")
    rating = await _rating(card)
    published_at = _parse_google_review_time(relative_time)
    return {
        "id": review_id,
        "author_name": author,
        "content": content,
        "rating": rating,
        "comment_time_raw": relative_time,
        "published_at": published_at.isoformat() if published_at else None,
        "commented_at": published_at.isoformat() if published_at else None,
        "like_count": 0,
        "reply_count": 0,
        "reaction_count": 0,
        "comment_type": "review",
        "raw_json": {
            "full_card_text": text,
            "place_url": place_url,
            "parser_strategy": parser_strategy,
        },
    }


def _parse_review_fallback_text(text: str) -> tuple[str, str, str]:
    tokens = text.split()
    if not tokens:
        return "", "", text
    author = tokens[0]
    time_match = re.search(
        r"(\d+\s+(?:minutes?|hours?|days?|weeks?|months?|years?)\s+ago|"
        r"\d+\s*(?:分鐘|小時|天|週|個月|年)前)",
        text,
        re.IGNORECASE,
    )
    if not time_match:
        return author, "", text
    relative_time = time_match.group(1)
    content = text[time_match.end() :].strip()
    content = re.sub(r"\bMore\b$", "", content, flags=re.IGNORECASE).strip()
    return author, relative_time, content or text


def _parse_google_review_time(value: str | None, *, now: datetime | None = None) -> datetime | None:
    if not value:
        return None
    now = now or datetime.now(timezone.utc)
    text = " ".join(value.strip().split()).casefold()
    match = re.search(r"(\d+)", text)
    amount = int(match.group(1)) if match else 1
    if any(token in text for token in ("minute", "分鐘")):
        return now - timedelta(minutes=amount)
    if any(token in text for token in ("hour", "小時")):
        return now - timedelta(hours=amount)
    if any(token in text for token in ("day", "天")):
        return now - timedelta(days=amount)
    if any(token in text for token in ("week", "週")):
        return now - timedelta(weeks=amount)
    if any(token in text for token in ("month", "個月")):
        return now - timedelta(days=amount * 30)
    if any(token in text for token in ("year", "年")):
        return now - timedelta(days=amount * 365)
    return None


async def _text(node, selector: str) -> str:
    try:
        element = await node.query_selector(selector)
        if not element:
            return ""
        return " ".join((await element.inner_text()).split())
    except Exception:
        return ""


async def _rating(card) -> float | None:
    try:
        elements = await card.query_selector_all("[aria-label]")
        for element in elements:
            label = await element.get_attribute("aria-label")
            if not label:
                continue
            lowered = label.lower()
            if "\u661f" not in label and "star" not in lowered:
                continue
            match = re.search(r"([\d.]+)", label)
            if match:
                return float(match.group(1))
        return None
    except Exception:
        return None


async def _card_url(card) -> str:
    try:
        link = await card.query_selector('a[href*="/maps/place"], a[href*="google.com/maps/place"]')
        if not link:
            return ""
        href = await link.get_attribute("href")
        return href or ""
    except Exception:
        return ""


async def _place_title(page) -> str:
    for selector in ("h1.DUwDvf", "h1"):
        value = await _text(page, selector)
        if value:
            return value
    try:
        title = await page.title()
        return title.replace(" - Google Maps", "").replace(" - Google \u5730\u5716", "").strip()
    except Exception:
        return ""


async def _is_google_maps_restricted(page) -> bool:
    try:
        body = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        return False
    return any(token in body for token in RESTRICTED_TEXT_TOKENS)


def _looks_like_reviews_control(value: str) -> bool:
    return any(token in value for token in REVIEWS_TOKENS)


def _reviews_url(url: str) -> str:
    if "!10e1" in url:
        return url
    if "/maps/place/" in url and "/@" in url:
        return url
    if "!16s" in url:
        return url.replace("!16s", "!10e1!16s", 1)
    return url


def _place_external_id(url: str) -> str | None:
    match = re.search(r"!1s([^!/?]+)", url)
    return match.group(1) if match else None


def _title_from_url(url: str) -> str:
    from urllib.parse import unquote, urlparse

    path = unquote(urlparse(url).path)
    match = re.search(r"/place/([^/]+)", path)
    return (match.group(1).replace("+", " ") if match else "").strip()


def _timed_out(started: float, max_minutes: float) -> bool:
    return (time.monotonic() - started) > (max_minutes * 60)


def _remaining_seconds(started: float, max_minutes: float) -> float:
    return max(0.0, (max_minutes * 60) - (time.monotonic() - started))


def _timeout_ms(started: float, max_minutes: float, cap_ms: int) -> int:
    remaining_ms = int(_remaining_seconds(started, max_minutes) * 1000)
    return max(1, min(cap_ms, remaining_ms))


async def _wait_for_remaining(page, *, started: float, max_minutes: float, milliseconds: int) -> None:
    remaining_ms = int(_remaining_seconds(started, max_minutes) * 1000)
    if remaining_ms <= 0:
        return
    await page.wait_for_timeout(min(milliseconds, remaining_ms))


def _build_google_maps_parser() -> argparse.ArgumentParser:
    parser_arg = argparse.ArgumentParser(description="Google Maps Adapter")
    parser_arg.add_argument("--url", default=None, help="Target Google Maps place/search URL")
    cli.add_common_crawler_args(parser_arg)
    parser_arg.add_argument("--google-maps-lookback-days", type=int, default=30)
    parser_arg.add_argument("--google-maps-diff-mode", choices=["fast", "strict"], default="fast")
    parser_arg.add_argument("--google-maps-max-reviews", type=int, default=None)
    parser_arg.add_argument("--google-maps-max-scroll", type=int, default=None)
    return parser_arg


async def main():
    return await run_from_args(_build_google_maps_parser().parse_args())


async def run_from_args(args):
    start_time = time.time()

    if not args.url:
        elapsed_time = time.time() - start_time
        error = "Google Maps crawler requires --url for a specific place."
        logger.error(error)
        return {
            "platform": "google_maps",
            "status": "failed",
            "inserted": 0,
            "cards_found": 0,
            "elapsed": elapsed_time,
            "error_message": error,
        }

    headless = str(args.headless).strip().lower() not in ("false", "0", "no")
    logger.info("==========================================")
    logger.info("Google Maps Adapter start")
    logger.info("target URL: %s", args.url)
    logger.info("keyword: %s", args.keyword)
    logger.info("date range: %s", args.date_range)
    logger.info("==========================================")

    task_keyword = getattr(args, "input_keyword", None) or ""
    max_scroll = args.google_maps_max_scroll if args.google_maps_max_scroll is not None else args.max_scroll
    crawl_runtime: dict = {}
    posts = await scrape_google_maps(
        args.url,
        task_keyword,
        max_scroll=max_scroll,
        max_minutes=args.max_minutes,
        headless=headless,
        runtime_diagnostics=crawl_runtime,
    )
    if _review_limit_enabled(args.google_maps_max_reviews):
        _limit_reviews(posts, max_reviews=args.google_maps_max_reviews)

    if args.google_maps_lookback_days is not None and args.google_maps_lookback_days < 0:
        raise ValueError("--google-maps-lookback-days must be >= 0. Use 0 for an unlimited crawl window.")
    window_start, window_end = _rolling_window(lookback_days=args.google_maps_lookback_days)
    place_urls = [normalize_place_url(post.get("post_url") or post.get("source_url") or post.get("url")) for post in posts]
    existing_index = await asyncio.to_thread(
        db.load_existing_google_review_index,
        place_urls,
        window_start=window_start,
        window_end=window_end,
    )
    delta = classify_google_reviews(
        posts,
        existing_index=existing_index,
        window_start=window_start,
        window_end=window_end,
        diff_mode=args.google_maps_diff_mode,
    )
    delta_posts = delta["posts"]
    place_posts = delta.get("place_posts") or delta_posts
    for post in place_posts:
        post["crawl_job_id"] = getattr(args, "crawl_job_id", None)
        post["service_task_id"] = getattr(args, "service_task_id", None)
    diagnostics = delta["diagnostics"]
    diagnostics["deadline_reached"] = bool(crawl_runtime.get("deadline_reached"))
    persistence_result = (
        None
        if args.dry_run or not place_posts
        else await asyncio.to_thread(db.save_google_reviews_with_result, place_posts)
    )
    persistence = (
        persistence_result.as_dict()
        if persistence_result is not None
        else {
            "canonical_posts_written": 0,
            "canonical_comments_written": 0,
            "post_metric_snapshots_written": 0,
            "comment_metric_snapshots_written": 0,
            "failed_stages": [],
            "stages": [],
        }
    )
    saved_count = persistence["canonical_posts_written"]
    canonical_comments_written = persistence["canonical_comments_written"]
    status = "success"
    error_type = None
    error_message = None
    if persistence_result is not None and persistence_result.status != "success":
        status = persistence_result.status
        error_type = persistence_result.error_type
        error_message = persistence_result.error_message
    elif not existing_index.available:
        status = "partial_success"
        error_type = "existing_index_unavailable"
        error_message = existing_index.error_message
    if diagnostics["deadline_reached"] and status == "success":
        status = "partial_success" if posts else "failed"
        error_type = "deadline_reached" if posts else "timeout"
        error_message = "Google Maps crawl reached its time budget; collected data was preserved."
    outcome = _google_maps_outcome(
        status=status,
        places_found=len(posts),
        reviews_scanned=diagnostics["reviews_scanned"],
        canonical_posts_written=saved_count,
        canonical_comments_written=canonical_comments_written,
        error_type=error_type,
    )

    elapsed_time = time.time() - start_time
    logger.info("==========================================")
    logger.info("Google Maps Adapter finished")
    logger.info("Total places with reviews   : %s", len(posts))
    logger.info("Existing records loaded     : %s", diagnostics["existing_records_loaded"])
    logger.info("Reviews scanned             : %s", diagnostics["reviews_scanned"])
    logger.info("New reviews                 : %s", diagnostics["new_reviews"])
    logger.info("Changed reviews             : %s", diagnostics["changed_reviews"])
    logger.info("Unchanged reviews           : %s", diagnostics["unchanged_reviews"])
    logger.info("Older reviews skipped       : %s", diagnostics["older_reviews_skipped"])
    logger.info("Delta reviews               : %s", diagnostics["delta_reviews"])
    logger.info("Total inserted              : %s", saved_count)
    logger.info("Persistence failed stages   : %s", persistence["failed_stages"])
    logger.info("Elapsed time                : %.2f seconds", elapsed_time)
    logger.info("==========================================")
    return {
        "platform": "google_maps",
        "status": status,
        "outcome": outcome,
        "technical_success": status in {"success", "partial_success"},
        "data_yield_success": saved_count > 0 or canonical_comments_written > 0,
        "inserted": saved_count,
        "cards_found": len(posts),
        "comments_found": diagnostics["comments_found"],
        **diagnostics,
        "error_type": error_type,
        "error_message": error_message,
        "places_saved": saved_count,
        "db_rows_written": saved_count,
        **{key: value for key, value in persistence.items() if key.endswith("_written")},
        "persistence": persistence,
        "elapsed": elapsed_time,
    }


def _limit_reviews(posts: list[dict], *, max_reviews: int) -> None:
    remaining = max_reviews
    for post in posts:
        reviews = post.get("reviews") or []
        if remaining <= 0:
            post["reviews"] = []
            post["comment_count"] = 0
            post["reaction_count"] = 0
            continue
        post["reviews"] = reviews[:remaining]
        post["comment_count"] = len(post["reviews"])
        post["reaction_count"] = len(post["reviews"])
        remaining -= len(post["reviews"])


def _review_limit_enabled(max_reviews: int | None) -> bool:
    return max_reviews is not None and max_reviews > 0


def _google_maps_outcome(
    *,
    status: str,
    places_found: int,
    reviews_scanned: int,
    canonical_posts_written: int,
    canonical_comments_written: int,
    error_type: str | None,
) -> str:
    if status == "failed":
        return "failed"
    if error_type in {"timeout", "restricted", "captcha", "blocked"}:
        return "blocked"
    if status == "partial_success":
        return "partial_success"
    if canonical_posts_written > 0 or canonical_comments_written > 0:
        return "success_with_data"
    if places_found > 0 or reviews_scanned > 0:
        return "success_no_changes"
    return "success_no_results"


from adapters.base import CommandModuleCrawler
from adapters.registry import CrawlerRegistry


class GoogleMapsCrawler(CommandModuleCrawler):
    def __init__(self) -> None:
        super().__init__("google_maps", "adapters.google_maps.crawler")


CrawlerRegistry.register("google_maps", GoogleMapsCrawler)


if __name__ == "__main__":
    asyncio.run(main())
