from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RiskSignal:
    detected: bool
    reason: str | None = None
    matched_text: str | None = None


class RiskDetector:
    RISK_TERMS: tuple[tuple[str, str], ...] = (
        ("captcha", "captcha"),
        ("verification", "verification"),
        ("login", "login"),
        ("please log in", "login"),
        ("請登入", "login"),
        ("驗證", "verification"),
        ("429", "http_429"),
        ("403", "http_403"),
    )

    @classmethod
    async def check(cls, page_or_text: Any) -> RiskSignal:
        text = await cls._extract_text(page_or_text)
        normalized = text.lower()
        for term, reason in cls.RISK_TERMS:
            if term.lower() in normalized:
                return RiskSignal(True, reason=reason, matched_text=term)
        return RiskSignal(False)

    @staticmethod
    async def _extract_text(page_or_text: Any) -> str:
        if page_or_text is None:
            return ""
        if isinstance(page_or_text, str):
            return page_or_text
        status = getattr(page_or_text, "status", None)
        if status in {403, 429}:
            return str(status)
        content = getattr(page_or_text, "content", None)
        if callable(content):
            value = content()
            if hasattr(value, "__await__"):
                value = await value
            return str(value)
        text_content = getattr(page_or_text, "text_content", None)
        if callable(text_content):
            value = text_content("body")
            if hasattr(value, "__await__"):
                value = await value
            return str(value)
        inner_text = getattr(page_or_text, "inner_text", None)
        if callable(inner_text):
            value = inner_text("body")
            if hasattr(value, "__await__"):
                value = await value
            return str(value)
        return str(page_or_text)

