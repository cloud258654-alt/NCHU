from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.rolling_delta import coerce_datetime, datetime_identity, normalize_text, normalize_url, safe_int, stable_hash


POST_METRIC_FIELDS = ("like_count", "comment_count", "share_count", "reaction_count")
REPLY_METRIC_FIELDS = ("like_count", "reply_count", "reaction_count")


@dataclass(frozen=True)
class ExistingThreadsRecord:
    identity_key: str
    post_id: str | None
    normalized_url: str
    content_hash: str
    metric_hash: str
    reply_identities: dict[str, tuple[str, str]]


@dataclass(frozen=True)
class ExistingThreadsIndex:
    by_post_id: dict[str, ExistingThreadsRecord]
    by_normalized_url: dict[str, ExistingThreadsRecord]
    available: bool
    source: str
    records_loaded: int
    error_message: str | None = None


def normalize_threads_url(value: str | None) -> str:
    return normalize_url(value).rstrip("/") + "/" if value else ""


def threads_post_identity(post: dict[str, Any]) -> tuple[str, str]:
    post_id = post.get("external_id") or post.get("post_id") or post.get("platform_post_id")
    if post_id:
        return f"threads:post:id:{post_id}", "strong"
    return f"threads:post:url:{normalize_threads_url(post.get('post_url') or post.get('source_url') or post.get('link'))}", "medium"


def threads_content_hash(post: dict[str, Any]) -> str:
    return stable_hash(
        [
            normalize_text(post.get("content")),
            normalize_text(post.get("author_id") or post.get("author_name")),
            datetime_identity(post.get("post_time") or post.get("published_at")),
        ]
    )


def threads_metric_hash(post: dict[str, Any]) -> str:
    return stable_hash([safe_int(post.get(field)) for field in POST_METRIC_FIELDS])


def threads_reply_identity(reply: dict[str, Any], *, root_post_id: str | None, root_url: str | None) -> tuple[str, str]:
    reply_id = reply.get("external_id") or reply.get("post_id")
    if reply_id:
        return f"threads:reply:id:{reply_id}", "strong"
    reply_url = normalize_threads_url(reply.get("source_url") or reply.get("url"))
    if reply_url and reply_url != normalize_threads_url(root_url):
        return f"threads:reply:url:{reply_url}", "medium"
    return (
        f"threads:reply:hash:{stable_hash([root_post_id or normalize_threads_url(root_url), normalize_text(reply.get('author_id') or reply.get('author_name')), normalize_text(reply.get('content')), datetime_identity(reply.get('commented_at') or reply.get('published_at'))])}",
        "weak",
    )


def threads_reply_content_hash(reply: dict[str, Any]) -> str:
    return stable_hash(
        [
            normalize_text(reply.get("author_id") or reply.get("author_name")),
            normalize_text(reply.get("content")),
            datetime_identity(reply.get("commented_at") or reply.get("published_at")),
        ]
    )


def threads_reply_metric_hash(reply: dict[str, Any]) -> str:
    return stable_hash([safe_int(reply.get(field)) for field in REPLY_METRIC_FIELDS])


def existing_threads_record_from_row(row: dict[str, Any], replies: list[dict[str, Any]] | None = None) -> ExistingThreadsRecord:
    post = {
        "external_id": row.get("platform_post_id") or row.get("external_id"),
        "post_url": row.get("link") or row.get("source_url"),
        "content": row.get("content"),
        "author_id": row.get("author_id"),
        "author_name": row.get("author_name"),
        "post_time": row.get("published_at"),
        "like_count": row.get("like_count"),
        "comment_count": row.get("comment_count"),
        "share_count": row.get("share_count"),
        "reaction_count": row.get("reaction_count"),
    }
    identity_key, _ = threads_post_identity(post)
    reply_index: dict[str, tuple[str, str]] = {}
    for reply in replies or []:
        identity, _ = threads_reply_identity(
            reply,
            root_post_id=post.get("external_id"),
            root_url=post.get("post_url"),
        )
        reply_index[identity] = (threads_reply_content_hash(reply), threads_reply_metric_hash(reply))
    return ExistingThreadsRecord(
        identity_key=identity_key,
        post_id=post.get("external_id"),
        normalized_url=normalize_threads_url(post.get("post_url")),
        content_hash=threads_content_hash(post),
        metric_hash=threads_metric_hash(post),
        reply_identities=reply_index,
    )


def classify_threads_posts(
    posts: list[dict[str, Any]],
    *,
    existing_index: ExistingThreadsIndex,
    window_start: datetime,
    window_end: datetime,
) -> dict[str, Any]:
    diagnostics = {
        "triggered_at": window_end.isoformat(),
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "items_discovered": len(posts),
        "items_scanned": 0,
        "items_in_window": 0,
        "existing_records_loaded": existing_index.records_loaded,
        "new_items": 0,
        "changed_content_items": 0,
        "changed_metric_items": 0,
        "unchanged_items": 0,
        "unknown_delta_items": 0,
        "older_items_skipped": 0,
        "unknown_time_skipped": 0,
        "delta_items": 0,
        "db_rows_written": 0,
        "ai_items_enqueued": 0,
        "stop_reason": None,
    }
    if not existing_index.available:
        diagnostics["error_type"] = "existing_index_unavailable"
        diagnostics["error_message"] = existing_index.error_message

    delta_posts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in posts:
        diagnostics["items_scanned"] += 1
        post_time = coerce_datetime(post.get("post_time"))
        if post_time is None:
            diagnostics["unknown_time_skipped"] += 1
            continue
        if post_time > window_end or post_time < window_start:
            diagnostics["older_items_skipped"] += 1
            continue
        diagnostics["items_in_window"] += 1

        identity_key, confidence = threads_post_identity(post)
        if identity_key in seen:
            continue
        seen.add(identity_key)
        post["identity_key"] = identity_key
        post["identity_confidence"] = confidence
        post["content_hash"] = threads_content_hash(post)
        post["metric_hash"] = threads_metric_hash(post)

        existing = _lookup_existing(post, existing_index)
        status = "new"
        changed_fields: list[str] = []
        if not existing_index.available:
            status = "unknown_delta"
            diagnostics["unknown_delta_items"] += 1
        elif existing is None:
            diagnostics["new_items"] += 1
            changed_fields = ["post"]
        else:
            if post["content_hash"] != existing.content_hash:
                changed_fields.append("content")
            if post["metric_hash"] != existing.metric_hash:
                changed_fields.extend([field for field in POST_METRIC_FIELDS if field not in changed_fields])
            if changed_fields:
                status = "changed"
                if "content" in changed_fields:
                    diagnostics["changed_content_items"] += 1
                else:
                    diagnostics["changed_metric_items"] += 1
            else:
                status = "unchanged"

        original_replies = [reply for reply in post.get("comments") or [] if isinstance(reply, dict)]
        delta_replies = _classify_replies(original_replies, post=post, existing=existing)
        if status == "unchanged" and not delta_replies:
            diagnostics["unchanged_items"] += 1
            continue

        delta_post = {**post, "comments": delta_replies if existing is not None and status == "unchanged" else original_replies}
        delta_post["delta_status"] = status
        delta_post["changed_fields"] = changed_fields
        if status in {"new", "unknown_delta"} or "content" in changed_fields:
            diagnostics["ai_items_enqueued"] += 1
        delta_posts.append(delta_post)

    diagnostics["delta_items"] = len(delta_posts)
    return {"posts": delta_posts, "diagnostics": diagnostics}


def _lookup_existing(post: dict[str, Any], index: ExistingThreadsIndex) -> ExistingThreadsRecord | None:
    post_id = post.get("external_id") or post.get("post_id")
    if post_id and post_id in index.by_post_id:
        return index.by_post_id[post_id]
    normalized = normalize_threads_url(post.get("post_url") or post.get("source_url"))
    return index.by_normalized_url.get(normalized)


def _classify_replies(
    replies: list[dict[str, Any]],
    *,
    post: dict[str, Any],
    existing: ExistingThreadsRecord | None,
) -> list[dict[str, Any]]:
    if existing is None:
        return replies
    delta: list[dict[str, Any]] = []
    for reply in replies:
        identity_key, confidence = threads_reply_identity(
            reply,
            root_post_id=post.get("external_id"),
            root_url=post.get("post_url") or post.get("source_url"),
        )
        reply["identity_key"] = identity_key
        reply["identity_confidence"] = confidence
        reply["content_hash"] = threads_reply_content_hash(reply)
        reply["metric_hash"] = threads_reply_metric_hash(reply)
        existing_hashes = existing.reply_identities.get(identity_key)
        if existing_hashes is None:
            reply["delta_status"] = "new"
            reply["changed_fields"] = ["reply"]
            delta.append(reply)
        elif existing_hashes != (reply["content_hash"], reply["metric_hash"]):
            reply["delta_status"] = "changed"
            reply["changed_fields"] = ["content"] if existing_hashes[0] != reply["content_hash"] else ["metrics"]
            delta.append(reply)
        else:
            reply["delta_status"] = "unchanged"
            reply["changed_fields"] = []
    return delta
