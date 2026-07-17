from __future__ import annotations

from bs4 import BeautifulSoup, FeatureNotFound


def parse_ptt_index_html(html: str) -> list[dict]:
    """Parse PTT board index or board search HTML into article link records."""

    try:
        soup = BeautifulSoup(html, "lxml")
    except FeatureNotFound:
        soup = BeautifulSoup(html, "html.parser")
    items: list[dict] = []

    for row in soup.select("div.r-ent"):
        title_node = row.select_one("div.title a")
        author_node = row.select_one("div.author")
        date_node = row.select_one("div.date")

        if not title_node:
            continue

        href = title_node.get("href")
        if not href:
            continue

        post_url = f"https://www.ptt.cc{href}" if href.startswith("/") else href
        items.append(
            {
                "title": title_node.get_text(strip=True),
                "author_name": author_node.get_text(strip=True) if author_node else "",
                "post_time_raw": date_node.get_text(strip=True) if date_node else "",
                "post_url": post_url,
            }
        )

    return items
