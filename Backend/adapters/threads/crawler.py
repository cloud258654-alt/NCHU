import sys
import os
import re
import argparse
import asyncio
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import quote

# 載入 core 共用模組
import core.cli as cli
import core.count_parser as count_parser
import core.logger as logger_mod
import core.time_filter as time_filter
import core.supabase as db
from core.rolling_delta import rolling_window, unlimited_or_positive
from core.query import build_query_attempts, contains_business_name
import core.runtime_settings as runtime_settings
from core.search_config import load_config
from core.search_engines import create_engine, engine_names_for
from core.search_models import SearchQuery
from adapters.threads.delta import classify_threads_posts, normalize_threads_url as normalize_threads_delta_url

# 設定輸出編碼為 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 選取器定義 (依據 Threads 網頁結構修正)
POST_CARD_SELECTOR = "div[data-pressable-container='true']"
POST_LINK_SELECTOR = "a[href*='/post/']"
POST_AUTHOR_LINK = "a[href*='/@']"
POST_CONTENT_SELECTOR = "span[dir='auto']"
POST_TIME_SELECTOR = "time"
THREADS_DEBUG_ROOT = Path("debug") / "threads"
THREADS_LOGIN_TOKENS = ("log in", "login", "登入", "instagram")
THREADS_CAPTCHA_TOKENS = ("captcha", "unusual traffic", "verification", "verify", "驗證")
THREADS_RESTRICTED_TOKENS = ("restricted", "content unavailable", "not available", "受限", "無法使用")

logger = logger_mod.get_logger("adapters.threads")


def parse_counts(card_text: str) -> tuple[int, int, int]:
    """解析統計數據，回傳 (likes, replies, reposts)。"""
    likes = 0
    replies = 0
    reposts = 0

    like_match = re.search(r"([\d.,]+[KkMm]?)\s*(?:likes?|個讚|讚)", card_text, re.IGNORECASE)
    reply_match = re.search(r"([\d.,]+[KkMm]?)\s*(?:repl(y|ies)|則回覆|回覆|留言)", card_text, re.IGNORECASE)
    repost_match = re.search(r"([\d.,]+[KkMm]?)\s*(?:reposts?|次轉發|轉發)", card_text, re.IGNORECASE)

    if like_match:
        likes = count_parser.parse_count(like_match.group(1))
    if reply_match:
        replies = count_parser.parse_count(reply_match.group(1))
    if repost_match:
        reposts = count_parser.parse_count(repost_match.group(1))

    return likes, replies, reposts


# 3.1 URL 標準化
def normalize_threads_url(url: str) -> str:
    """標準化 Threads 網址，去除 Query string 並補上結尾斜線。"""
    if not url:
        return ""
    if url.startswith("/"):
        url = f"https://www.threads.com{url}"
    url = url.split("?")[0].rstrip("/") + "/"
    return url


# 3.2 從 URL 解析 username / post_id
def parse_threads_post_identity(post_url: str) -> dict:
    """解析 Threads 貼文網址中的 username 與 post_id。"""
    match = re.search(r"threads\.(?:net|com)/@([^/]+)/post/([^/?#]+)/?", post_url)
    if not match:
        return {"username": None, "post_id": None}
    return {
        "username": match.group(1),
        "post_id": match.group(2),
    }


# 4. 抽出共用 content cleaning
async def discover_threads_urls(keyword: str, args, *, max_results: int = 50) -> list[str]:
    config = load_config(searxng_url=getattr(args, "searxng_url", None))
    urls: list[str] = []
    seen: set[str] = set()
    queries = [
        f'site:threads.com/@/post "{keyword}"',
        f'"{keyword}" site:threads.com',
        f'site:threads.net/@/post "{keyword}"',
        f'"{keyword}" site:threads.net',
    ]
    for engine_name in engine_names_for(getattr(args, "engine", "duckduckgo"), config):
        for query_text in queries:
            if len(urls) >= max_results:
                break
            try:
                engine = create_engine(engine_name, config)
                results = await engine.search(
                    SearchQuery(
                        keyword=query_text,
                        engine=engine_name,
                        max_results=max(max_results - len(urls), 10),
                    )
                )
            except Exception as exc:
                logger.info("Threads discovery engine failed: engine=%s error=%s", engine_name, exc)
                continue
            for result in results:
                normalized = normalize_threads_url(result.url)
                ident = parse_threads_post_identity(normalized)
                if not ident.get("post_id") or normalized in seen:
                    continue
                seen.add(normalized)
                urls.append(normalized)
                if len(urls) >= max_results:
                    break
    return urls


def _threads_context_options() -> dict:
    options = {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "locale": "zh-TW",
        "viewport": {"width": 1280, "height": 800},
    }
    storage_state = Path(runtime_settings.THREADS_STORAGE_STATE_PATH)
    if storage_state.exists():
        options["storage_state"] = str(storage_state)
        logger.info("Threads using Playwright storage_state: %s", storage_state)
    return options


async def extract_threads_card_content(card) -> str:
    """清理 Threads 卡片（貼文或留言）中的 UI 噪音。"""
    elems = await card.query_selector_all("span[dir='auto']")
    texts = []

    noise_texts = {
        "翻譯",
        "See translation",
        "查看更多",
        "更多",
        "View more",
        "Show more",
        "See more",
        "回覆",
        "Replies",
        "Reply",
        "讚",
        "likes",
        "reposts",
    }

    for elem in elems:
        try:
            txt = (await elem.inner_text()).strip()
        except Exception:
            continue

        if not txt:
            continue

        if txt in noise_texts:
            continue

        if txt.endswith("翻譯"):
            txt = txt[:-2].strip()

        if txt.endswith("See translation"):
            txt = txt[:-15].strip()

        # 純日期
        if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", txt):
            continue

        # 純數字 / 統計數
        if re.match(r"^[\d.,]+[KkMm萬千]?$", txt):
            continue

        # 太短且像 UI 的字串
        if txt in {"·", "•", "…"}:
            continue

        if txt and txt not in texts:
            texts.append(txt)

    return "\n".join(texts).strip()


def validate_post_payload(post: dict) -> bool:
    """驗證每筆貼文是否符合輸出標準。"""
    url = post.get("post_url") or post.get("source_url")
    content = post.get("content")
    author_id = post.get("author_id") or post.get("username")
    author_name = post.get("author_name")

    if not url or not url.strip():
        return False
    if not content or not content.strip():
        return False
    if (not author_id or not author_id.strip()) and (not author_name or not author_name.strip()):
        return False
    return True


def _matches_threads_business(text: str, business_name: str | None) -> bool:
    return contains_business_name(text, business_name)


def _threads_search_queries(keyword: str, args) -> list[str]:
    """Try business plus optional intent, then business alone."""

    business_name = getattr(args, "business_name", None)
    input_keyword = getattr(args, "input_keyword", None)
    if business_name:
        return build_query_attempts(
            business_name=business_name,
            keyword=input_keyword,
        )
    return [keyword.strip()] if keyword and keyword.strip() else []


async def bypass_login_wall(page) -> None:
    """移除頁面上遮擋滾動與操作的登入彈窗。"""
    try:
        await page.evaluate("""
            () => {
                const modals = Array.from(document.querySelectorAll('div[role="dialog"], div[role="presentation"]')).filter(el => {
                    const text = el.innerText || '';
                    return text.includes("透過 Threads 暢所欲言") || text.includes("使用 Instagram") || text.includes("登入");
                });
                for (const m of modals) {
                    m.remove();
                }
                
                const overlays = Array.from(document.querySelectorAll('div')).filter(el => {
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' && (parseInt(style.zIndex) > 10 || style.zIndex === 'auto')) {
                        const text = el.innerText || '';
                        if (text.includes("透過 Threads 暢所欲言") || text.includes("使用 Instagram")) {
                            el.remove();
                        }
                    }
                });
                
                document.body.style.overflow = 'auto';
                document.body.style.position = 'static';
                document.documentElement.style.overflow = 'auto';
            }
        """)
    except Exception as je:
        logger.debug(f"Bypassing login wall JS error: {je}")


def _new_threads_page_diagnostics() -> dict:
    return {
        "page_title": "",
        "current_url": "",
        "body_text_sample": "",
        "login_wall_detected": False,
        "captcha_detected": False,
        "restricted_detected": False,
        "selector_counts": {
            "article": 0,
            "post_links": 0,
            "known_containers": 0,
        },
        "debug_artifacts": {},
    }


def _classify_threads_body(body_text: str, current_url: str = "") -> dict:
    text = f"{body_text}\n{current_url}".casefold()
    return {
        "login_wall_detected": any(token.casefold() in text for token in THREADS_LOGIN_TOKENS),
        "captcha_detected": any(token.casefold() in text for token in THREADS_CAPTCHA_TOKENS),
        "restricted_detected": any(token.casefold() in text for token in THREADS_RESTRICTED_TOKENS),
    }


async def _collect_threads_page_diagnostics(page) -> dict:
    diagnostics = _new_threads_page_diagnostics()
    try:
        diagnostics["page_title"] = await page.title()
    except Exception:
        pass
    diagnostics["current_url"] = getattr(page, "url", "") or ""
    try:
        body_text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        body_text = ""
    diagnostics["body_text_sample"] = body_text[:2000]
    diagnostics.update(_classify_threads_body(body_text, diagnostics["current_url"]))
    selector_counts = diagnostics["selector_counts"]
    for key, selector in (
        ("article", "article"),
        ("post_links", POST_LINK_SELECTOR),
        ("known_containers", POST_CARD_SELECTOR),
    ):
        try:
            selector_counts[key] = await page.locator(selector).count()
        except Exception:
            selector_counts[key] = 0
    return diagnostics


async def _wait_for_threads_search_results(page, args, *, timeout: int = 15000) -> bool:
    """Wait for a real post link, not a generic pressable login control."""

    try:
        await page.wait_for_selector(POST_LINK_SELECTOR, timeout=timeout)
        return True
    except Exception:
        page_diagnostics = await _collect_threads_page_diagnostics(page)
        body_text = page_diagnostics["body_text_sample"]
        args.threads_page_diagnostics = page_diagnostics
        if (
            page_diagnostics["login_wall_detected"]
            or page_diagnostics["captcha_detected"]
            or page_diagnostics["restricted_detected"]
        ):
            args.threads_page_diagnostics = await _capture_threads_debug_artifacts(
                page,
                args,
                reason="blocked",
                diagnostics=page_diagnostics,
            )
            raise RuntimeError("Threads login/session blocked crawler")
        if "查無結果" in body_text or "No results" in body_text:
            logger.warning("Threads search returned no post links.")
            return False

        args.threads_page_diagnostics = await _capture_threads_debug_artifacts(
            page,
            args,
            reason="zero_post_links",
            diagnostics=page_diagnostics,
        )
        raise RuntimeError("Threads post-link selector changed, timed out, or was blocked")


async def _capture_threads_debug_artifacts(page, args, *, reason: str, diagnostics: dict | None = None) -> dict:
    diagnostics = diagnostics or await _collect_threads_page_diagnostics(page)
    crawl_job_id = getattr(args, "crawl_job_id", None) or "no-crawl-job"
    safe_job_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(crawl_job_id)).strip("-") or "no-crawl-job"
    debug_dir = THREADS_DEBUG_ROOT / safe_job_id
    debug_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = debug_dir / "screenshot.png"
    html_path = debug_dir / "page.html"
    diagnostics_path = debug_dir / "diagnostics.json"
    try:
        await page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception as exc:
        diagnostics.setdefault("debug_errors", []).append(f"screenshot: {exc}")
    try:
        html_path.write_text(await page.content(), encoding="utf-8")
    except Exception as exc:
        diagnostics.setdefault("debug_errors", []).append(f"html: {exc}")
    diagnostics["debug_artifacts"] = {
        "reason": reason,
        "directory": str(debug_dir),
        "screenshot": str(screenshot_path),
        "html": str(html_path),
        "diagnostics": str(diagnostics_path),
    }
    diagnostics_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return diagnostics


# 3.3 詳細頁 replies 抓取
async def fetch_threads_replies(context, post_url: str, *, max_scroll: int, max_minutes: float) -> list[dict]:
    """開啟每篇貼文的詳細頁面，抓取可見的 replies/comments。"""
    page = await context.new_page()
    # 注入刪除 webdriver 屬性腳本，避免防爬自動化檢測
    await page.add_init_script("delete navigator.__proto__.webdriver;")
    
    replies = []
    seen = set()
    started = time.time()

    try:
        await page.goto(post_url, wait_until="domcontentloaded", timeout=60000)

        # 等待可能的貼文卡片
        try:
            await page.wait_for_selector("div[data-pressable-container='true']", timeout=15000)
        except Exception:
            logger.warning("Threads detail page has no visible cards: %s", post_url)
            return []

        # 如果出現 login wall / verification，要記錄，不要假裝成功
        body_text = await page.locator("body").inner_text(timeout=10000)
        lower_body = body_text.lower()
        if "log in" in lower_body or "登入" in body_text or "驗證" in body_text:
            logger.warning("Threads detail page may be login-gated: %s", post_url)

        # 嘗試展開更多留言 / 更多內容
        expand_labels = [
            "查看更多",
            "更多",
            "View more",
            "Show more",
            "See more",
            "查看回覆",
            "View replies",
            "Show replies",
        ]

        for _ in range(3):
            for label in expand_labels:
                try:
                    await bypass_login_wall(page)
                    buttons = page.get_by_text(label, exact=False)
                    count = await buttons.count()
                    for i in range(min(count, 5)):
                        try:
                            await buttons.nth(i).click(timeout=1500)
                            await page.wait_for_timeout(500)
                        except Exception:
                            pass
                except Exception:
                    pass

        # 滾動詳細頁，讓 replies 載入
        last_count = 0
        stagnant = 0
        effective_max_scroll = max_scroll if max_scroll > 0 else 1000
        for _ in range(effective_max_scroll):
            if time.time() - started > max_minutes * 60:
                break

            await bypass_login_wall(page)
            cards = await page.query_selector_all("div[data-pressable-container='true']")
            current_count = len(cards)

            if current_count <= last_count:
                stagnant += 1
            else:
                stagnant = 0

            last_count = current_count

            await page.mouse.wheel(0, 1800)
            await page.wait_for_timeout(1200)

            if stagnant >= 3:
                break

        await bypass_login_wall(page)
        cards = await page.query_selector_all("div[data-pressable-container='true']")
        root_norm = normalize_threads_url(post_url)

        for idx, card in enumerate(cards):
            try:
                card_text = (await card.inner_text()).strip()
                if not card_text:
                    continue

                # 找卡片中的 Threads post/reply URL
                link_elem = await card.query_selector("a[href*='/post/']")
                href = await link_elem.get_attribute("href") if link_elem else ""
                reply_url = normalize_threads_url(href) if href else ""

                # 跳過原始貼文
                if reply_url and reply_url == root_norm:
                    continue

                # 詳細頁第一張通常是 root post，若沒有 reply_url，也先跳過第一張
                if idx == 0:
                    continue

                author_id = None
                author_name = None

                author_elem = await card.query_selector("a[href*='/@']")
                if author_elem:
                    author_href = await author_elem.get_attribute("href")
                    if author_href:
                        m = re.search(r"/@([^/?#]+)", author_href)
                        if m:
                            author_id = m.group(1)
                    try:
                        author_name = (await author_elem.inner_text()).strip()
                    except Exception:
                        author_name = author_id

                content = await extract_threads_card_content(card)
                if not content:
                    continue

                # 避免把按鈕文字、原文、空內容寫入 comments
                if len(content.strip()) < 2:
                    continue

                # reply external id
                external_id = None
                if reply_url:
                    ident = parse_threads_post_identity(reply_url)
                    external_id = ident.get("post_id")

                dedupe_basis = reply_url or f"{author_id}|{content[:80]}"
                if dedupe_basis in seen:
                    continue
                seen.add(dedupe_basis)

                like_count, reply_count, repost_count = parse_counts(card_text)

                comment = {
                    "external_id": external_id,
                    "source_url": reply_url or post_url,
                    "author_id": author_id,
                    "author_name": author_name or author_id,
                    "content": content,
                    "comment_time_raw": None,
                    "commented_at": None,
                    "like_count": like_count,
                    "reply_count": reply_count,
                    "reaction_count": like_count,
                    "comment_type": "reply",
                    "raw_json": {
                        "platform": "threads",
                        "source_post_url": post_url,
                        "reply_url": reply_url,
                        "card_text": card_text,
                    },
                }

                replies.append(comment)

            except Exception as exc:
                logger.debug("Failed to parse Threads reply card: %s", exc)

    finally:
        await page.close()

    return replies


async def parse_visible_cards_helper(page, all_parsed_posts_map, keyword, args, crawl_started_at) -> None:
    cards = await page.query_selector_all(POST_CARD_SELECTOR)
    for idx, card in enumerate(cards):
        try:
            link_elem = await card.query_selector(POST_LINK_SELECTOR)
            if not link_elem:
                continue
            href = await link_elem.get_attribute("href")
            if not href:
                continue

            post_url = normalize_threads_url(href)
            ident = parse_threads_post_identity(post_url)
            username = ident.get("username")
            post_id = ident.get("post_id")

            if not post_id or post_url in all_parsed_posts_map:
                continue

            author_elem = await card.query_selector(POST_AUTHOR_LINK)
            author_name = username
            if author_elem:
                author_text = await author_elem.inner_text()
                if author_text:
                    author_name = author_text.strip()

            cleaned_content = await extract_threads_card_content(card)

            post_time_raw = "Unknown"
            post_time = None
            time_elem = await card.query_selector(POST_TIME_SELECTOR)
            if time_elem:
                datetime_str = await time_elem.get_attribute("datetime")
                title_str = await time_elem.get_attribute("title")
                post_time_raw = title_str if title_str else (datetime_str if datetime_str else "Unknown")

                if datetime_str:
                    try:
                        post_time = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
                    except ValueError:
                        try:
                            post_time = datetime.fromtimestamp(float(datetime_str), tz=timezone.utc)
                        except ValueError:
                            pass

            card_text = await card.inner_text()
            likes, replies, reposts = parse_counts(card_text)

            # If the page is a search result page, we trust the platform search relevance.
            # Otherwise, we apply the business matching filter to prevent noise.
            is_search_page = "search" in (getattr(page, "url", "") or "")
            if not is_search_page:
                required_business = getattr(args, "business_name", None) or keyword
                if not _matches_threads_business(f"{cleaned_content}\n{card_text}", required_business):
                    continue

            if not time_filter.should_keep_post(post_time, post_time_raw, args, "threads"):
                continue

            threads_metrics = {
                "like_count": likes,
                "reply_count": replies,
                "repost_count": reposts,
                "quote_count": 0,
                "view_count": 0,
            }

            raw_json = {
                "platform": "threads",
                "scraped_url": post_url,
                "username": username,
                "threads_metrics": threads_metrics,
                "metrics": {
                    "like_count": likes,
                    "comment_count": replies,
                    "share_count": reposts,
                    "reaction_count": likes
                },
                "comments": []
            }

            post_data = {
                "post_url": post_url,
                "external_id": post_id,
                "author_id": username,
                "author_name": author_name,
                "title": f"Threads 貼文: {username}",
                "content": cleaned_content,
                "post_time_raw": post_time_raw,
                "post_time": post_time,
                "like_count": likes,
                "comment_count": replies,
                "share_count": reposts,
                "reaction_count": likes,
                "threads_metrics": threads_metrics,
                "keyword": keyword,
                "date_range": getattr(args, "date_range", "all"),
                "source": "threads",
                "raw_json": raw_json,
                "crawl_started_at": crawl_started_at,
                "crawl_finished_at": None
            }

            if validate_post_payload(post_data):
                all_parsed_posts_map[post_url] = post_data
        except Exception as card_err:
            logger.debug(f"解析卡片錯誤: {card_err}")


async def scrape_threads(keyword: str, max_scroll: int, max_minutes: float, headless: bool, args) -> list[dict]:
    from playwright.async_api import async_playwright

    search_queries = _threads_search_queries(keyword, args)
    primary_query = search_queries[0] if search_queries else keyword

    all_parsed_posts_map = {}
    soft_deadline = time.monotonic() + (max_minutes * 60)
    args.threads_deadline_reached = False
    crawl_started_at = datetime.now(timezone.utc).isoformat()
    discovery_limit = _threads_post_limit(args) or 50
    discovered_urls = await discover_threads_urls(primary_query, args, max_results=min(discovery_limit, 100))
    if time.monotonic() >= soft_deadline:
        args.threads_deadline_reached = True
        return []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--lang=zh-TW"
            ]
        )
        context = await browser.new_context(**_threads_context_options())
        page = await context.new_page()
        await page.add_init_script("delete navigator.__proto__.webdriver;")

        try:
            for candidate_url in discovered_urls:
                if time.monotonic() >= soft_deadline:
                    args.threads_deadline_reached = True
                    break
                try:
                    await page.goto(
                        candidate_url,
                        wait_until="domcontentloaded",
                        timeout=_remaining_timeout_ms(soft_deadline, 60000),
                    )
                    await page.wait_for_selector(
                        POST_LINK_SELECTOR,
                        timeout=_remaining_timeout_ms(soft_deadline, 10000),
                    )
                    await parse_visible_cards_helper(page, all_parsed_posts_map, keyword, args, crawl_started_at)
                except Exception as exc:
                    logger.debug("Threads discovered URL parse failed: url=%s error=%s", candidate_url, exc)

            for query_index, search_query in enumerate(search_queries):
                if time.monotonic() >= soft_deadline:
                    args.threads_deadline_reached = True
                    break
                url = f"https://www.threads.com/search?q={quote(search_query)}"
                logger.info("Threads search attempt %s/%s: %s", query_index + 1, len(search_queries), url)
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=_remaining_timeout_ms(soft_deadline, 60000),
                )

                # A generic pressable container also exists on the login wall.
                if not await _wait_for_threads_search_results(
                    page,
                    args,
                    timeout=_remaining_timeout_ms(soft_deadline, 15000),
                ):
                    continue

                await parse_visible_cards_helper(page, all_parsed_posts_map, keyword, args, crawl_started_at)
                is_last_query = query_index == len(search_queries) - 1
                if not all_parsed_posts_map and not is_last_query:
                    logger.info("Threads strict query had no relevant posts; falling back to business name.")
                    continue

                logger.info("開始執行滾動載入貼文...")
                scroll_rounds = 0
                last_count = len(all_parsed_posts_map)
                same_count = 0
                effective_max_scroll = max_scroll if max_scroll > 0 else 1000
                while same_count < 2 and scroll_rounds < effective_max_scroll:
                    if time.monotonic() >= soft_deadline:
                        args.threads_deadline_reached = True
                        logger.warning("動態滾動達到最大時間限制，終止滾動。")
                        break
                    if "login" in page.url:
                        args.threads_page_diagnostics = await _capture_threads_debug_artifacts(
                            page,
                            args,
                            reason="login_url",
                        )
                        logger.warning("偵測到頁面被重新導向至登入頁面，終止滾動。")
                        break

                    await bypass_login_wall(page)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    scroll_rounds += 1

                    import random
                    delay = int((2.5 + random.uniform(-0.5, 0.5)) * 1000)
                    await page.wait_for_timeout(min(delay, _remaining_timeout_ms(soft_deadline, delay)))
                    await parse_visible_cards_helper(page, all_parsed_posts_map, keyword, args, crawl_started_at)
                    current_count = len(all_parsed_posts_map)
                    logger.info(f"scroll round: {scroll_rounds}, collected posts: {current_count}")
                    if current_count == last_count:
                        same_count += 1
                    else:
                        same_count = 0
                        last_count = current_count

                if len(all_parsed_posts_map) >= discovery_limit:
                    logger.info("Reached threads post limit (%s), stopping search.", discovery_limit)
                    break

            # Phase B: post detail page replies extraction
            posts_list = list(all_parsed_posts_map.values())
            logger.info(f"貼文列表收集完畢，共 {len(posts_list)} 篇貼文。")
            for idx, post in enumerate(posts_list):
                if time.monotonic() >= soft_deadline:
                    args.threads_deadline_reached = True
                    break
                post_url = post["post_url"]
                
                # Check --fetch-comments CLI argument
                if getattr(args, "fetch_comments", False):
                    logger.info(f"開始開啟貼文詳細頁爬取 replies: {post_url}")
                    replies = await fetch_threads_replies(
                        context,
                        post_url,
                        max_scroll=_threads_reply_scroll_limit(args),
                        max_minutes=max(
                            0.01,
                            min((soft_deadline - time.monotonic()) / 60, args.max_minutes, 3),
                        ),
                    )
                    post["comments"] = replies
                    post["raw_json"]["comments"] = replies
                    post["raw_json"]["reply_count_scraped"] = len(replies)
                    post["comment_count"] = len(replies)
                    logger.info(f"貼文 {idx+1}/{len(posts_list)}：成功獲取 {len(replies)} 則留言。")
                else:
                    post["comments"] = []
                    post["raw_json"]["comments"] = []
                    post["comment_count"] = 0

            logger.info(f"爬取結束，共成功解析並過濾出 {len(all_parsed_posts_map)} 篇貼文與其留言。")

        except Exception as e:
            if time.monotonic() >= soft_deadline:
                args.threads_deadline_reached = True
                logger.warning("Threads crawl stopped at its soft deadline: %s", e)
            else:
                logger.error(f"爬取 Threads 過程中發生嚴重錯誤: {e}")
                raise
        finally:
            await browser.close()

    return list(all_parsed_posts_map.values())


def _remaining_timeout_ms(deadline: float, cap_ms: int) -> int:
    remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000)
    return max(1, min(cap_ms, remaining_ms))


def _build_threads_parser() -> argparse.ArgumentParser:
    parser_arg = argparse.ArgumentParser(description="Threads Adapter (Search Crawler)")
    cli.add_common_crawler_args(parser_arg)
    return parser_arg


async def main():
    return await run_from_args(_build_threads_parser().parse_args())


async def run_from_args(args):
    start_time = time.time()

    # 參數解析
    if args.lookback_days is not None and args.lookback_days < 0:
        raise ValueError("--lookback-days must be >= 0. Use 0 for an unlimited crawl window.")
    if args.max_minutes <= 0:
        raise ValueError("--max-minutes must be > 0.")

    headless_str = str(args.headless).strip().lower()
    headless = headless_str not in ("false", "0", "no")

    logger.info("==========================================")
    logger.info("Threads Adapter 啟動")
    logger.info(f"關鍵字: {args.keyword}")
    logger.info(f"時間範圍: {args.date_range}")
    logger.info(f"自訂天數: {args.since_days}")
    logger.info(f"開始日期: {args.start_date} | 結束日期: {args.end_date}")
    logger.info("==========================================")

    # 執行爬取
    max_retries = 3
    posts = []
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"執行爬取任務 (第 {attempt}/{max_retries} 次嘗試)...")
            posts = await scrape_threads(
                keyword=args.keyword,
                max_scroll=_threads_scroll_limit(args),
                max_minutes=args.max_minutes,
                headless=headless,
                args=args
            )
            break
        except Exception as err:
            logger.error(f"第 {attempt} 次嘗試發生錯誤: {err}")
            if attempt == max_retries:
                logger.error("已達最大重試次數，終止爬蟲。")
                page_diagnostics = getattr(args, "threads_page_diagnostics", _new_threads_page_diagnostics())
                blocked = bool(
                    page_diagnostics.get("login_wall_detected")
                    or page_diagnostics.get("captcha_detected")
                    or page_diagnostics.get("restricted_detected")
                )
                elapsed_time = time.time() - start_time
                return {
                    "platform": "threads",
                    "status": "failed",
                    "outcome": "blocked" if blocked else "failed",
                    "technical_success": False,
                    "data_yield_success": False,
                    "inserted": 0,
                    "cards_found": 0,
                    "comments_found": 0,
                    "canonical_posts_written": 0,
                    "canonical_comments_written": 0,
                    "post_metric_snapshots_written": 0,
                    "comment_metric_snapshots_written": 0,
                    "elapsed": elapsed_time,
                    "error_type": "blocked" if blocked else "threads_crawl_failed",
                    "error_message": str(err),
                    "diagnostics": {
                        "page": page_diagnostics,
                        "items_discovered_before_cap": 0,
                    },
                }
            await asyncio.sleep(5)

    discovered_cards = len(posts)
    post_limit = _threads_post_limit(args)
    if post_limit is not None and post_limit > 0:
        posts = posts[:post_limit]

    window_start, window_end = rolling_window(lookback_days=args.lookback_days)
    candidate_urls = [normalize_threads_delta_url(post.get("post_url") or post.get("source_url")) for post in posts]
    existing_index = await asyncio.to_thread(
        db.load_existing_threads_index,
        window_start,
        window_end,
        candidate_urls=[url for url in candidate_urls if url],
    )
    delta_result = classify_threads_posts(
        posts,
        existing_index=existing_index,
        window_start=window_start,
        window_end=window_end,
    )
    diagnostics = {
        "rolling_delta": delta_result["diagnostics"],
        "items_discovered_before_cap": discovered_cards,
        "page": getattr(args, "threads_page_diagnostics", _new_threads_page_diagnostics()),
    }
    posts = delta_result["posts"]
    for post in posts:
        post["crawl_job_id"] = getattr(args, "crawl_job_id", None)
        post["service_task_id"] = getattr(args, "service_task_id", None)
    total_cards = len(posts)
    matched_keyword = len(posts)
    within_date_range = len(posts)

    # 補上結束時間
    crawl_finished_at = datetime.now(timezone.utc).isoformat()
    for post in posts:
        post["crawl_finished_at"] = crawl_finished_at
        if post["post_time"] and isinstance(post["post_time"], datetime):
            post["post_time"] = post["post_time"].isoformat()

    # 存入資料庫 (若為 dry-run 則不呼叫 Supabase)
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
    status = "success"
    error_type = None
    error_message = None
    if posts and not args.dry_run:
        persistence_result = await asyncio.to_thread(db.save_threads_posts_with_result, posts)
        persistence = persistence_result.as_dict()
        saved_count = persistence["canonical_posts_written"]
        diagnostics["rolling_delta"]["db_rows_written"] = saved_count
        if persistence_result.status != "success":
            status = persistence_result.status
            error_type = persistence_result.error_type
            error_message = persistence_result.error_message
        for post in posts:
            preview = post["content"][:30].replace("\n", " ") if post["content"] else "(無文字內容)"
            try:
                safe_preview = preview.encode(sys.stdout.encoding or 'utf-8', errors='replace').decode(sys.stdout.encoding or 'utf-8')
            except Exception:
                safe_preview = preview
            print(f"[OK] {safe_preview}")

    deadline_reached = bool(getattr(args, "threads_deadline_reached", False))
    diagnostics["deadline_reached"] = deadline_reached
    if deadline_reached and status == "success":
        status = "partial_success" if posts else "failed"
        error_type = "deadline_reached" if posts else "timeout"
        error_message = "Threads crawl reached its time budget; collected data was preserved."

    # export JSONL (只輸出清理後、準備寫入的資料，排除 environment secrets)
    if posts and getattr(args, "export_jsonl", None):
        export_path = Path(args.export_jsonl)
        export_path.parent.mkdir(parents=True, exist_ok=True)
        with export_path.open("w", encoding="utf-8") as f:
            for post in posts:
                f.write(json.dumps(post, ensure_ascii=False, default=str) + "\n")
        logger.info(f"Cleaned posts exported to JSONL: {export_path}")

    elapsed_time = time.time() - start_time
    outcome = _threads_outcome(
        status=status,
        diagnostics=diagnostics,
        discovered_cards=discovered_cards,
        canonical_posts_written=persistence["canonical_posts_written"],
        canonical_comments_written=persistence["canonical_comments_written"],
    )

    # 輸出統計
    logger.info("==========================================")
    logger.info("Threads Adapter 執行完畢")
    logger.info(f"Total cards found          : {total_cards}")
    logger.info(f"Total parsed               : {total_cards}")
    logger.info(f"Total matched keyword      : {matched_keyword}")
    logger.info(f"Total within date range    : {within_date_range}")
    logger.info("Existing records loaded    : %s", diagnostics["rolling_delta"]["existing_records_loaded"])
    logger.info("Delta posts                : %s", diagnostics["rolling_delta"]["delta_items"])
    logger.info(f"Total inserted             : {saved_count}")
    logger.info(f"Elapsed time               : {elapsed_time:.2f} seconds")
    logger.info("==========================================")

    # 輸出 Dry-run 摘要資訊至 CLI
    if args.dry_run:
        print("\n=== DRY RUN SUMMARY ===")
        print(f"Platform: threads")
        print(f"Query keyword: {args.keyword}")
        print(f"Total cards found: {total_cards}")
        print(f"Total valid posts: {len(posts)}")
        print(f"Total missing URL: 0")
        print(f"Total missing content: 0")
        print(f"Total duplicate URL: 0")
        print(f"Sample posts (up to 5):")
        for i, post in enumerate(posts[:5]):
            print(f"  [{i+1}] {post['author_name']} (@{post['author_id']}): {post['post_url']}")
            print(f"      Content: {post['content'][:60]}...")
            comments = post["raw_json"].get("comments", [])
            print(f"      Comments count: {len(comments)}")
            for j, c in enumerate(comments[:2]):
                print(f"         - Comment [{j+1}] by {c['author_name']} (@{c['author_id']}): {c['content'][:40]}... (likes: {c['like_count']})")
        print("=======================\n")

    return {
        "platform": "threads",
        "status": status,
        "outcome": outcome,
        "technical_success": status in {"success", "partial_success"},
        "data_yield_success": persistence["canonical_posts_written"] > 0 or persistence["canonical_comments_written"] > 0,
        "inserted": saved_count,
        "cards_found": total_cards,
        "comments_found": sum(len(post.get("comments") or []) for post in posts),
        "ai_items_enqueued": diagnostics["rolling_delta"]["ai_items_enqueued"],
        "elapsed": elapsed_time,
        "error_type": error_type,
        "error_message": error_message,
        **{key: value for key, value in persistence.items() if key.endswith("_written")},
        "persistence": persistence,
        "diagnostics": diagnostics,
    }


def _threads_scroll_limit(args) -> int:
    platform_limit = unlimited_or_positive(getattr(args, "platform_max_scroll", None))
    threads_limit = unlimited_or_positive(getattr(args, "threads_max_scroll", None), fallback=platform_limit)
    if threads_limit is None:
        threads_limit = unlimited_or_positive(getattr(args, "max_scroll", 10), fallback=10)
    return 0 if threads_limit == 0 else max(1, threads_limit)


def _threads_reply_scroll_limit(args) -> int:
    scroll_limit = _threads_scroll_limit(args)
    if scroll_limit == 0:
        return 0
    return max(2, min(scroll_limit, 8))


def _threads_post_limit(args) -> int | None:
    platform_limit = unlimited_or_positive(getattr(args, "platform_max_results", None))
    threads_limit = unlimited_or_positive(getattr(args, "threads_max_posts", None), fallback=platform_limit)
    if threads_limit is None:
        threads_limit = unlimited_or_positive(getattr(args, "max_results", 50), fallback=50)
    if threads_limit == 0:
        return None
    return max(1, threads_limit)


def _threads_outcome(
    *,
    status: str,
    diagnostics: dict,
    discovered_cards: int,
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
    if discovered_cards > 0:
        return "partial_success"
    return "success_no_results"


# Backward compatibility aliases for unit tests
def standardize_threads_url_info(url: str) -> tuple[str, str, str]:
    normalized = normalize_threads_url(url)
    ident = parse_threads_post_identity(normalized)
    return normalized, ident["username"] or "unknown", ident["post_id"] or ""


def clean_threads_content(content: str) -> str:
    if not content:
        return ""
    lines = content.split("\n")
    cleaned_lines = []
    noise_texts = {
        "翻譯", "See translation", "查看更多", "更多",
        "View more", "Show more", "See more", "回覆", "Replies", "Reply", "讚", "likes", "reposts"
    }
    for line in lines:
        txt = line.strip()
        if not txt or txt in noise_texts:
            continue
        if txt.endswith("翻譯"):
            txt = txt[:-2].strip()
        if txt.endswith("See translation"):
            txt = txt[:-15].strip()
        if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", txt):
            continue
        if re.match(r"^[\d.,]+[KkMm萬千]?$", txt):
            continue
        if txt in {"·", "•", "…"}:
            continue
        if txt:
            cleaned_lines.append(txt)
    return "\n".join(cleaned_lines).strip()


from adapters.base import CommandModuleCrawler
from adapters.registry import CrawlerRegistry


class ThreadsCrawler(CommandModuleCrawler):
    def __init__(self) -> None:
        super().__init__("threads", "adapters.threads.crawler")


CrawlerRegistry.register("threads", ThreadsCrawler)


if __name__ == "__main__":
    asyncio.run(main())
