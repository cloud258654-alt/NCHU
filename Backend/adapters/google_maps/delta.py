from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from core.supabase import ExistingGoogleReviewIndex, ExistingReviewRecord


METRIC_FIELDS = ("like_count", "reply_count", "reaction_count")


def normalize_place_url(value: str | None) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    query = urlencode(
        [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key not in {"authuser", "entry"}],
        doseq=True,
    )
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def normalize_review_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    normalized = " ".join(normalized.split())
    return normalized.strip().casefold()


def google_review_identity(review: dict[str, Any], *, place_url: str) -> tuple[str, str]:
    review_id = review.get("id") or review.get("external_id")
    if review_id:
        return f"google_maps:review:id:{review_id}", "strong"

    author = normalize_review_text(review.get("author_name") or review.get("author"))
    published_at = _datetime_identity(review.get("published_at") or review.get("commented_at"))
    rating = _rating_identity(review.get("rating"))
    normalized_place = normalize_place_url(place_url)
    if published_at:
        return f"google_maps:review:medium:{_digest([normalized_place, author, published_at, rating])}", "medium"

    content = normalize_review_text(review.get("content") or review.get("text") or review.get("review"))
    return f"google_maps:review:weak:{_digest([normalized_place, author, content])}", "weak"


def content_hash(review: dict[str, Any]) -> str:
    return _digest(
        [
            normalize_review_text(review.get("author_name") or review.get("author")),
            normalize_review_text(review.get("content") or review.get("text") or review.get("review")),
            _rating_identity(review.get("rating")),
            _datetime_identity(review.get("published_at") or review.get("commented_at")),
        ]
    )


def metric_hash(review: dict[str, Any]) -> str:
    return _digest([str(_safe_int(review.get(field))) for field in METRIC_FIELDS])


def lightweight_hash(review: dict[str, Any]) -> str:
    return _digest(
        [
            normalize_review_text((review.get("content") or review.get("text") or review.get("review") or "")[:300]),
            _rating_identity(review.get("rating")),
            str(_safe_int(review.get("like_count"))),
            str(_safe_int(review.get("reply_count"))),
        ]
    )


def existing_record_from_review(review: dict[str, Any], *, place_url: str) -> ExistingReviewRecord:
    identity_key, _ = google_review_identity(review, place_url=place_url)
    return ExistingReviewRecord(
        crawl_comment_id=str(review.get("crawl_comment_id") or ""),
        review_id=str(review.get("id") or review.get("external_id") or "") or None,
        dedupe_key=str(review.get("dedupe_key") or identity_key),
        content_hash=content_hash(review),
        metric_hash=metric_hash(review),
        lightweight_hash=lightweight_hash(review),
        author_name=str(review.get("author_name") or review.get("author") or ""),
        rating=_safe_float(review.get("rating")),
        published_at=_coerce_datetime(review.get("published_at") or review.get("commented_at")),
        content=str(review.get("content") or review.get("text") or review.get("review") or ""),
        like_count=_safe_int(review.get("like_count")),
        reply_count=_safe_int(review.get("reply_count")),
        reaction_count=_safe_int(review.get("reaction_count")),
    )


def classify_google_reviews(
    posts: list[dict[str, Any]],
    *,
    existing_index: ExistingGoogleReviewIndex,
    window_start: datetime,
    window_end: datetime,
    diff_mode: str = "fast",
) -> dict[str, Any]:
    diagnostics = {
        "places_scanned": len(posts),
        "baseline_places": 0,
        "incremental_places": 0,
        "existing_records_loaded": existing_index.records_loaded,
        "existing_index_available": existing_index.available,
        "existing_index_source": existing_index.source,
        "reviews_scanned": 0,
        "reviews_in_window": 0,
        "baseline_reviews": 0,
        "new_reviews": 0,
        "changed_reviews": 0,
        "changed_content_reviews": 0,
        "changed_metric_reviews": 0,
        "unchanged_reviews": 0,
        "older_reviews_skipped": 0,
        "duplicate_reviews": 0,
        "delta_reviews": 0,
        "comments_found": 0,
        "ai_items_enqueued": 0,
        "change_status": "no_changes",
        "stop_reason": None,
    }
    if not existing_index.available:
        diagnostics["error_type"] = "existing_index_unavailable"
        diagnostics["error_message"] = existing_index.error_message

    delta_posts: list[dict[str, Any]] = []
    place_posts: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    diff_mode = diff_mode if diff_mode in {"fast", "strict"} else "fast"

    for post in posts:
        place_url = post.get("post_url") or post.get("source_url") or post.get("url")
        normalized_place = normalize_place_url(place_url)
        place_index = existing_index.by_place.get(normalized_place, {})
        baseline_mode = existing_index.available and not place_index
        if baseline_mode:
            diagnostics["baseline_places"] += 1
        else:
            diagnostics["incremental_places"] += 1
        delta_reviews: list[dict[str, Any]] = []

        for review in post.get("reviews") or []:
            if not isinstance(review, dict):
                continue
            diagnostics["reviews_scanned"] += 1
            identity_key, confidence = google_review_identity(review, place_url=place_url)
            if identity_key in seen_identities:
                diagnostics["duplicate_reviews"] += 1
                continue
            seen_identities.add(identity_key)

            review["identity_key"] = identity_key
            review["identity_confidence"] = confidence
            review["content_hash"] = content_hash(review)
            review["metric_hash"] = metric_hash(review)
            review["lightweight_hash"] = lightweight_hash(review)

            if baseline_mode:
                review["delta_status"] = "baseline"
                review["changed_fields"] = ["review"]
                diagnostics["baseline_reviews"] += 1
                diagnostics["ai_items_enqueued"] += 1
                delta_reviews.append(review)
                continue

            published_at = _coerce_datetime(review.get("published_at") or review.get("commented_at"))
            if published_at and not (window_start <= published_at <= window_end):
                diagnostics["older_reviews_skipped"] += 1
                continue
            diagnostics["reviews_in_window"] += 1

            if not existing_index.available:
                review["delta_status"] = "unknown_delta"
                review["changed_fields"] = []
                delta_reviews.append(review)
                continue

            existing = place_index.get(identity_key)
            if existing is None:
                review["delta_status"] = "new"
                review["changed_fields"] = ["review"]
                diagnostics["new_reviews"] += 1
                diagnostics["ai_items_enqueued"] += 1
                delta_reviews.append(review)
                continue

            changed_fields = _changed_fields(review, existing, diff_mode=diff_mode)
            if changed_fields:
                review["delta_status"] = "changed"
                review["changed_fields"] = changed_fields
                diagnostics["changed_reviews"] += 1
                if any(field in changed_fields for field in ("content", "rating", "author", "published_at")):
                    diagnostics["changed_content_reviews"] += 1
                    diagnostics["ai_items_enqueued"] += 1
                else:
                    diagnostics["changed_metric_reviews"] += 1
                delta_reviews.append(review)
            else:
                review["delta_status"] = "unchanged"
                review["changed_fields"] = []
                diagnostics["unchanged_reviews"] += 1

        place_post = {**post, "reviews": delta_reviews}
        place_post["comment_count"] = len(delta_reviews)
        place_post["reaction_count"] = len(delta_reviews)
        place_posts.append(place_post)
        if delta_reviews:
            delta_posts.append(place_post)

    diagnostics["delta_reviews"] = sum(len(post.get("reviews") or []) for post in delta_posts)
    diagnostics["comments_found"] = diagnostics["delta_reviews"]
    if diagnostics["delta_reviews"]:
        diagnostics["change_status"] = "changes_detected"
    if not existing_index.available:
        diagnostics["change_status"] = "partial_success"
    return {"posts": delta_posts, "place_posts": place_posts, "review_delta_posts": delta_posts, "diagnostics": diagnostics}


def _changed_fields(review: dict[str, Any], existing: ExistingReviewRecord, *, diff_mode: str) -> list[str]:
    if diff_mode == "fast" and review.get("lightweight_hash") == existing.lightweight_hash:
        return []
    if review.get("content_hash") == existing.content_hash and review.get("metric_hash") == existing.metric_hash:
        return []

    changed: list[str] = []
    if review.get("content_hash") != existing.content_hash:
        if normalize_review_text(review.get("content")) != normalize_review_text(existing.content):
            changed.append("content")
        if _rating_identity(review.get("rating")) != _rating_identity(existing.rating):
            changed.append("rating")
        if normalize_review_text(review.get("author_name")) != normalize_review_text(existing.author_name):
            changed.append("author")
        if _datetime_identity(review.get("published_at")) != _datetime_identity(existing.published_at):
            changed.append("published_at")
        if not changed:
            changed.append("content")
    if review.get("metric_hash") != existing.metric_hash:
        for field in METRIC_FIELDS:
            if _safe_int(review.get(field)) != getattr(existing, field):
                changed.append(field)
    return changed


def _digest(parts: list[str]) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _datetime_identity(value: Any) -> str:
    dt = _coerce_datetime(value)
    return dt.astimezone(timezone.utc).isoformat() if dt else ""


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _rating_identity(value: Any) -> str:
    rating = _safe_float(value)
    return "" if rating is None else f"{rating:.3f}"


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        match = re.search(r"\d+", str(value))
        return int(match.group(0)) if match else 0


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
