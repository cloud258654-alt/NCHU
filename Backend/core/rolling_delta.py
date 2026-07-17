from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def rolling_window(*, lookback_days: int | None, triggered_at: datetime | None = None) -> tuple[datetime, datetime]:
    if lookback_days is not None and lookback_days < 0:
        raise ValueError("lookback_days must be >= 0")
    window_end = coerce_datetime(triggered_at) or datetime.now(timezone.utc)
    window_start = (
        datetime(1970, 1, 1, tzinfo=timezone.utc)
        if lookback_days in (None, 0)
        else window_end - timedelta(days=lookback_days)
    )
    return window_start, window_end


def coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif value:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def normalize_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(normalized.split()).strip().casefold()


def stable_hash(parts: list[Any]) -> str:
    normalized = [str(part or "") for part in parts]
    return hashlib.sha256("\x1f".join(normalized).encode("utf-8")).hexdigest()


def datetime_identity(value: Any) -> str:
    dt = coerce_datetime(value)
    return dt.isoformat() if dt else ""


def safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def normalize_url(value: str | None) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    query = urlencode(
        [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key not in {"utm_source", "utm_medium", "utm_campaign", "fbclid"}],
        doseq=True,
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def unlimited_or_positive(value: Any, *, fallback: int | None = None) -> int | None:
    if value is None:
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    if parsed < 0:
        return fallback
    return parsed


def under_limit(count: int, limit: int | None) -> bool:
    return limit is None or limit == 0 or count < limit
