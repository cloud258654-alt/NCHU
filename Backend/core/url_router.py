from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class RouteMatch:
    platform: str
    parser_name: str | None = None


class URLRouter:
    """Map discovered URLs to currently active MVP platform adapters."""

    ROUTES: tuple[tuple[str, RouteMatch], ...] = (
        ("threads.com", RouteMatch("threads", "ThreadsParser")),
        ("threads.net", RouteMatch("threads", "ThreadsParser")),
        ("ptt.cc", RouteMatch("ptt", "PTTParser")),
        ("google.com/maps", RouteMatch("google_maps", "GoogleMapsParser")),
        ("goo.gl/maps", RouteMatch("google_maps", "GoogleMapsParser")),
    )

    @classmethod
    def route(cls, url: str) -> RouteMatch:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        normalized = f"{host}{parsed.path}".lower()
        for pattern, match in cls.ROUTES:
            if pattern in normalized:
                return match
        return RouteMatch("web", None)

    @classmethod
    def detect_platform(cls, url: str) -> str:
        return cls.route(url).platform
