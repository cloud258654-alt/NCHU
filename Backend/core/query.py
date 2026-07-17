from __future__ import annotations


def build_search_query(*, business_name: str | None, keyword: str | None) -> str:
    """Build the crawler discovery query from business identity and optional intent."""

    business = (business_name or "").strip()
    extra_keyword = (keyword or "").strip()
    parts: list[str] = []
    if business:
        parts.append(business)
    if extra_keyword and extra_keyword not in parts:
        parts.append(extra_keyword)
    return " ".join(parts)


def build_query_attempts(
    *,
    business_name: str | None,
    keyword: str | None,
    business_only: bool = False,
) -> list[str]:
    """Build at most two in-memory queries, from specific to broad."""

    business = " ".join((business_name or "").split())
    extra_keyword = " ".join((keyword or "").split())
    if not business:
        return [extra_keyword] if extra_keyword else []
    if business_only:
        return [business]

    combined = build_search_query(business_name=business, keyword=extra_keyword)
    return [combined, business] if combined != business else [business]


def contains_business_name(text: str | None, business_name: str | None) -> bool:
    """Return true only when text contains the normalized business identity."""

    folded_text = _compact_identity(text)
    folded_business = _compact_identity(business_name)
    return bool(folded_text and folded_business and folded_business in folded_text)


def _compact_identity(value: str | None) -> str:
    return "".join(ch for ch in (value or "").casefold() if ch.isalnum())
