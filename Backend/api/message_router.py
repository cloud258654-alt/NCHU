from __future__ import annotations

import re
import unicodedata

_GENERIC_COMMANDS = {
    "查詢",
    "查詢評價",
    "查詢最新評價",
    "最新評價",
    "網路評價",
    "評價報告",
    "網路評價報告",
    "更新評價",
    "更新報告",
}

_PREFIX_PATTERN = re.compile(
    r"^(?:請|麻煩|可以)?\s*(?:幫我)?\s*(?:查詢|查一下|搜尋|分析|更新)\s*[:：]?\s*",
    re.IGNORECASE,
)
_SUFFIX_PATTERN = re.compile(
    r"\s*(?:的)?\s*(?:最新)?\s*(?:網路)?\s*(?:評價報告|評價|評論|風評)\s*$",
    re.IGNORECASE,
)


def extract_business_name(message_text: str | None) -> str | None:
    """Extract a store/business name from a LINE text message.

    A plain store name is returned unchanged. Lightweight command wrappers such
    as ``查詢 文章牛肉湯 評價`` are removed. Generic commands without a store
    name return ``None`` so the caller can fall back to the user's bound store.
    """

    if not message_text:
        return None

    text = unicodedata.normalize("NFKC", message_text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip("\"'「」『』【】[]()（）<>《》,，。.!！?？:：;；")
    if not text or (text.startswith("[") and text.endswith("]")):
        return None

    candidate = _PREFIX_PATTERN.sub("", text, count=1)
    candidate = _SUFFIX_PATTERN.sub("", candidate, count=1)
    candidate = candidate.strip(" \"'「」『』【】[]()（）<>《》,，。.!！?？:：;；")

    if not candidate or candidate in _GENERIC_COMMANDS:
        return None
    return candidate[:255]
