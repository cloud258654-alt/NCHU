from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_text(
    url: str,
    *,
    params: dict[str, str | int | None] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> str:
    target = _with_query(url, params or {})
    request_headers = {"User-Agent": DEFAULT_USER_AGENT, **(headers or {})}
    request = Request(target, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def fetch_json(
    url: str,
    *,
    params: dict[str, str | int | None] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 20,
) -> object:
    return json.loads(fetch_text(url, params=params, headers=headers, timeout=timeout))


def _with_query(url: str, params: dict[str, str | int | None]) -> str:
    filtered = {key: value for key, value in params.items() if value is not None}
    if not filtered:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(filtered)}"
