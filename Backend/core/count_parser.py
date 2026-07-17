from __future__ import annotations

import re


def parse_count(text: str) -> int:
    """Parse common social count formats such as 1.2K, 3萬, or 1,500."""

    if not text:
        return 0
    cleaned = text.strip().replace(",", "")
    match = re.search(r"([\d.]+)\s*([萬万亿億WwKkMmB])?", cleaned)
    if not match:
        return 0
    number = float(match.group(1))
    unit = (match.group(2) or "").upper()
    if unit in {"W", "萬", "万"}:
        return int(number * 10_000)
    if unit == "K":
        return int(number * 1_000)
    if unit == "M":
        return int(number * 1_000_000)
    if unit in {"億", "亿"}:
        return int(number * 100_000_000)
    if unit == "B":
        return int(number * 1_000_000_000)
    return int(number)
