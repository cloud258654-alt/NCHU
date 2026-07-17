from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any


POST_METRIC_FIELDS = {
    "like_count",
    "reaction_count",
    "comment_count",
    "share_count",
    "view_count",
    "average_rating",
    "rating_count",
}


def standardize_crawled_post(
    item: dict[str, Any],
    *,
    platform: str,
    keyword: str | None,
    crawl_job_id: str | None = None,
    service_task_id: str | None = None,
    parsed_time: datetime | str | None = None,
) -> dict[str, Any]:
    """Normalize platform/search payloads into the crawl_posts write shape."""

    source_url = item.get("source_url") or item.get("url") or item.get("post_url")
    return {
        "crawl_job_id": crawl_job_id or item.get("crawl_job_id"),
        "platform": platform,
        "keyword": keyword,
        "source_url": source_url,
        "external_id": item.get("external_id") or item.get("id"),
        "title": item.get("title"),
        "author_name": item.get("author_name") or item.get("author"),
        "author_id": item.get("author_id") or item.get("username") or item.get("author_profile"),
        "content": item.get("content") or item.get("description") or item.get("snippet"),
        "post_time_raw": item.get("post_time_raw") or item.get("upload_date") or item.get("published_at"),
        "posted_at": parsed_time if parsed_time is not None else item.get("post_time") or item.get("posted_at"),
        "raw_json": item,
    }


def extract_post_metrics(item: dict[str, Any], *, captured_at: datetime | str | None = None) -> list[dict[str, Any]]:
    """Extract platform-specific evaluation metrics into post_metrics snapshots."""

    snapshot: dict[str, Any] = {"collected_at": captured_at}
    has_metric = False
    for source_field in POST_METRIC_FIELDS:
        value = item.get(source_field)
        if value is None:
            continue
        parsed = _coerce_metric_value(source_field, value)
        if parsed is None:
            continue
        snapshot[source_field] = parsed
        has_metric = True
    extra_data = _metric_extra_data(item)
    if extra_data:
        snapshot["extra_data"] = extra_data
        has_metric = True
    return [snapshot] if has_metric else []


def extract_comment_metrics(comment: dict[str, Any], *, collected_at: datetime | str | None = None) -> dict[str, Any] | None:
    metric: dict[str, Any] = {"collected_at": collected_at}
    has_metric = False
    for field in ("like_count", "reply_count", "reaction_count"):
        value = comment.get(field)
        if value is None:
            continue
        try:
            metric[field] = int(float(value))
        except (TypeError, ValueError):
            continue
        has_metric = True
    rating_value = comment.get("rating_value") if "rating_value" in comment else comment.get("rating")
    if rating_value is not None:
        parsed_rating = _coerce_metric_value("average_rating", rating_value)
        if parsed_rating is not None:
            metric["rating_value"] = parsed_rating
            has_metric = True
    return metric if has_metric else None


def extract_comments(item: dict[str, Any], *, platform: str, post_source_url: str | None) -> list[dict[str, Any]]:
    """Normalize replies/reviews embedded in a crawler payload into comment rows."""

    raw_comments = item.get("comments") or item.get("reviews") or []
    if isinstance(raw_comments, dict):
        raw_comments = [raw_comments]
    if not isinstance(raw_comments, list):
        return []

    comments = []
    for raw_comment in raw_comments:
        if not isinstance(raw_comment, dict):
            continue
        comment = standardize_comment(raw_comment, platform=platform, post_source_url=post_source_url)
        if comment is not None:
            comments.append(comment)
    return comments


def standardize_comment(
    item: dict[str, Any],
    *,
    platform: str,
    post_source_url: str | None,
) -> dict[str, Any] | None:
    content = item.get("content") or item.get("text") or item.get("body") or item.get("review")
    if not content:
        return None

    source_url = item.get("source_url") or item.get("url")
    external_id = item.get("external_id") or item.get("id")
    comment_time_raw = item.get("comment_time_raw") or item.get("published_at") or item.get("created_at")
    commented_at = item.get("commented_at") or item.get("published_at")
    dedupe_key = _comment_dedupe_key(
        platform=platform,
        post_source_url=post_source_url,
        source_url=source_url,
        external_id=external_id,
        author=item.get("author_name") or item.get("author"),
        content=content,
        comment_time_raw=comment_time_raw,
    )
    raw_json = item.get("raw_json") if isinstance(item.get("raw_json"), dict) else item
    return {
        "platform": platform,
        "dedupe_key": dedupe_key,
        "source_url": source_url,
        "external_id": external_id,
        "author_name": item.get("author_name") or item.get("author"),
        "author_id": item.get("author_id") or item.get("username"),
        "content": content,
        "rating_value": item.get("rating"),
        "sentiment_label": item.get("sentiment_label"),
        "comment_type": item.get("review_type") or item.get("comment_type") or "comment",
        "like_count": item.get("like_count", 0) or 0,
        "comment_time_raw": comment_time_raw,
        "commented_at": commented_at,
        "reply_count": item.get("reply_count"),
        "reaction_count": item.get("reaction_count"),
        "identity_key": item.get("identity_key"),
        "identity_confidence": item.get("identity_confidence"),
        "delta_status": item.get("delta_status"),
        "changed_fields": item.get("changed_fields"),
        "content_hash": item.get("content_hash"),
        "metric_hash": item.get("metric_hash"),
        "lightweight_hash": item.get("lightweight_hash"),
        "raw_json": raw_json,
    }


def _coerce_metric_value(field: str, value: Any) -> int | float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if field == "average_rating":
        return round(numeric, 2)
    return int(numeric)


def _metric_extra_data(item: dict[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {}
    google_summary = {
        key: item.get(key)
        for key in ("place_url", "place_id", "cid", "average_rating", "rating_count")
        if item.get(key) is not None
    }
    if google_summary:
        extra["google_maps_summary"] = google_summary
    for key in ("ptt_metrics", "threads_metrics"):
        if item.get(key) is not None:
            extra[key] = item[key]
    return extra


def standardize_search_result(result: dict[str, Any], *, keyword: str | None) -> dict[str, Any] | None:
    """Convert a routed search result record into the crawl_posts write shape."""

    platform = result.get("detected_platform") or result.get("platform")
    if platform in {None, "web"}:
        return None

    raw_json = result.get("raw_json") or {}
    payload = raw_json.get("parser_payload") if isinstance(raw_json, dict) else {}
    card = payload.get("raw_card") if isinstance(payload, dict) else {}
    if not isinstance(card, dict):
        card = {}

    item = {
        **card,
        "url": result["url"],
        "title": card.get("title") or result.get("title"),
        "snippet": card.get("snippet") or result.get("snippet"),
        "description": card.get("description") or result.get("snippet"),
        "service_task_id": result.get("service_task_id"),
        "crawl_job_id": result.get("crawl_job_id"),
    }
    post = standardize_crawled_post(item, platform=platform, keyword=keyword)
    post["raw_json"] = {
        "search_result": result,
        "parser_payload": payload or {},
        "raw_card": card,
    }
    return post


def _comment_dedupe_key(
    *,
    platform: str,
    post_source_url: str | None,
    source_url: str | None,
    external_id: Any,
    author: str | None,
    content: str,
    comment_time_raw: Any,
) -> str:
    if source_url:
        return f"{platform}:comment:url:{source_url}"
    if external_id:
        return f"{platform}:comment:id:{external_id}"
    payload = "|".join(
        [
            platform,
            post_source_url or "",
            author or "",
            str(comment_time_raw or ""),
            content,
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{platform}:comment:hash:{digest}"
