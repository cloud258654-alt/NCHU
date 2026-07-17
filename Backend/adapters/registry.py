from __future__ import annotations

from collections.abc import Iterable
from typing import Type

from adapters.base import Crawler


class CrawlerRegistry:
    """Platform crawler factory used by the runner."""

    _crawlers: dict[str, Type[Crawler]] = {}

    @classmethod
    def register(cls, platform: str, crawler_cls: Type[Crawler]) -> None:
        cls._crawlers[platform] = crawler_cls

    @classmethod
    def create(cls, platform: str) -> Crawler:
        try:
            crawler_cls = cls._crawlers[platform]
        except KeyError as exc:
            available = ", ".join(cls.available())
            raise ValueError(f"Unsupported platform '{platform}'. Available: {available}") from exc
        return crawler_cls()

    @classmethod
    def available(cls) -> Iterable[str]:
        return tuple(sorted(cls._crawlers))


def load_builtin_crawlers() -> None:
    """Import active MVP platform packages so they self-register."""

    import adapters.google_maps.crawler  # noqa: F401
    import adapters.ptt.crawler  # noqa: F401
    import adapters.threads.crawler  # noqa: F401
    import adapters.web.crawl4ai_crawler  # noqa: F401
