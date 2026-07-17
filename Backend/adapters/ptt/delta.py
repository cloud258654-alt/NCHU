from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.rolling_delta import coerce_datetime, datetime_identity, normalize_text, normalize_url, safe_int, stable_hash


POST_METRIC_FIELDS = ("push_count", "boo_count", "arrow_count", "comment_count", "reaction_count")
COMMENT_METRIC_FIELDS = ("like_count", "reply_count", "reaction_count")


@dataclass(frozen=True)
class ExistingPttRecord:
    identity_key: str
    external_id: str | None
    normalized_url: str
    content_hash: str
    metric_hash: str
    comment_identities: dict[str, tuple[str, str]]


@dataclass(frozen=True)
class ExistingPttIndex:
    by_external_id: dict[str, ExistingPttRecord]
    by_normalized_url: dict[str, ExistingPttRecord]
    available: bool
    source: str
    records_loaded: int
    error_message: str | None = None


def ptt_post_identity(post: dict[str, Any]) -> tuple[str, str]:
    external_id = post.get("external_id")
    if external_id:
        return f"ptt:post:id:{external_id}", "strong"
    normalized_url = normalize_ptt_url(post.get("post_url") or post.get("source_url"))
    return f"ptt:post:url:{normalized_url}", "medium"


def normalize_ptt_url(value: str | None) -> str:
    return normalize_url(value)


def ptt_content_hash(post: dict[str, Any]) -> str:
    return stable_hash(
        [
            normalize_text(post.get("title")),
            normalize_text(post.get("content")),
            normalize_text(post.get("author_id") or post.get("author_name")),
            datetime_identity(post.get("post_time") or post.get("published_at")),
        ]
    )


def ptt_metric_hash(post: dict[str, Any]) -> str:
    return stable_hash([safe_int(post.get(field)) for field in POST_METRIC_FIELDS])


def ptt_comment_identity(comment: dict[str, Any], *, root_external_id: str | None, root_url: str | None, sequence: int | None = None) -> tuple[str, str]:
    if comment.get("external_id"):
        return f"ptt:push:id:{comment['external_id']}", "strong"
    root = root_external_id or normalize_ptt_url(root_url)
    author = normalize_text(comment.get("author_id") or comment.get("author_name"))
    comment_type = normalize_text(comment.get("comment_type"))
    content = normalize_text(comment.get("content"))
    raw_time = normalize_text(comment.get("comment_time_raw") or comment.get("commented_at"))
    if sequence is not None:
        return f"ptt:push:seq:{stable_hash([root, sequence, author, comment_type, content, raw_time])}", "medium"
    return f"ptt:push:hash:{stable_hash([root, author, comment_type, content, raw_time])}", "weak"


def ptt_comment_content_hash(comment: dict[str, Any]) -> str:
    return stable_hash(
        [
            normalize_text(comment.get("author_id") or comment.get("author_name")),
            normalize_text(comment.get("comment_type")),
            normalize_text(comment.get("content")),
            normalize_text(comment.get("comment_time_raw") or comment.get("commented_at")),
        ]
    )


def ptt_comment_metric_hash(comment: dict[str, Any]) -> str:
    return stable_hash([safe_int(comment.get(field)) for field in COMMENT_METRIC_FIELDS])


def existing_ptt_record_from_row(row: dict[str, Any], comments: list[dict[str, Any]] | None = None) -> ExistingPttRecord:
    post = {
        "external_id": row.get("platform_post_id") or row.get("external_id"),
        "post_url": row.get("link") or row.get("source_url"),
        "title": row.get("title"),
        "content": row.get("content"),
        "author_id": row.get("author_id"),
        "author_name": row.get("author_name"),
        "post_time": row.get("published_at"),
        "push_count": ((row.get("extra_data") or {}).get("ptt_metrics") or {}).get("push_count"),
        "boo_count": ((row.get("extra_data") or {}).get("ptt_metrics") or {}).get("boo_count"),
        "arrow_count": ((row.get("extra_data") or {}).get("ptt_metrics") or {}).get("arrow_count"),
        "comment_count": row.get("comment_count"),
        "reaction_count": row.get("reaction_count"),
    }
    identity_key, _ = ptt_post_identity(post)
    comment_index: dict[str, tuple[str, str]] = {}
    for index, comment in enumerate(comments or []):
        identity, _ = ptt_comment_identity(
            comment,
            root_external_id=post.get("external_id"),
            root_url=post.get("post_url"),
            sequence=index,
        )
        comment_index[identity] = (ptt_comment_content_hash(comment), ptt_comment_metric_hash(comment))
    return ExistingPttRecord(
        identity_key=identity_key,
        external_id=post.get("external_id"),
        normalized_url=normalize_ptt_url(post.get("post_url")),
        content_hash=ptt_content_hash(post),
        metric_hash=ptt_metric_hash(post),
        comment_identities=comment_index,
    )


def classify_ptt_posts(
    posts: list[dict[str, Any]],
    *,
    existing_index: ExistingPttIndex,
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

        identity_key, confidence = ptt_post_identity(post)
        if identity_key in seen:
            continue
        seen.add(identity_key)
        post["identity_key"] = identity_key
        post["identity_confidence"] = confidence
        post["content_hash"] = ptt_content_hash(post)
        post["metric_hash"] = ptt_metric_hash(post)

        existing = _lookup_existing(post, existing_index)
        changed_fields: list[str] = []
        status = "new"
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

        original_comments = [comment for comment in post.get("comments") or [] if isinstance(comment, dict)]
        delta_comments = _classify_comments(original_comments, post=post, existing=existing)
        if status == "unchanged" and not delta_comments:
            diagnostics["unchanged_items"] += 1
            continue

        delta_post = {**post, "comments": delta_comments if existing is not None and status == "unchanged" else original_comments}
        delta_post["delta_status"] = status
        delta_post["changed_fields"] = changed_fields
        if status in {"new", "unknown_delta"} or "content" in changed_fields:
            diagnostics["ai_items_enqueued"] += 1
        delta_posts.append(delta_post)

    diagnostics["delta_items"] = len(delta_posts)
    return {"posts": delta_posts, "diagnostics": diagnostics}


def _lookup_existing(post: dict[str, Any], index: ExistingPttIndex) -> ExistingPttRecord | None:
    external_id = post.get("external_id")
    if external_id and external_id in index.by_external_id:
        return index.by_external_id[external_id]
    normalized = normalize_ptt_url(post.get("post_url") or post.get("source_url"))
    return index.by_normalized_url.get(normalized)


def _classify_comments(
    comments: list[dict[str, Any]],
    *,
    post: dict[str, Any],
    existing: ExistingPttRecord | None,
) -> list[dict[str, Any]]:
    if existing is None:
        return comments
    delta: list[dict[str, Any]] = []
    for index, comment in enumerate(comments):
        identity_key, confidence = ptt_comment_identity(
            comment,
            root_external_id=post.get("external_id"),
            root_url=post.get("post_url") or post.get("source_url"),
            sequence=index,
        )
        comment["identity_key"] = identity_key
        comment["identity_confidence"] = confidence
        comment["content_hash"] = ptt_comment_content_hash(comment)
        comment["metric_hash"] = ptt_comment_metric_hash(comment)
        existing_hashes = existing.comment_identities.get(identity_key)
        if existing_hashes is None:
            comment["delta_status"] = "new"
            comment["changed_fields"] = ["comment"]
            delta.append(comment)
        elif existing_hashes != (comment["content_hash"], comment["metric_hash"]):
            comment["delta_status"] = "changed"
            comment["changed_fields"] = ["content"] if existing_hashes[0] != comment["content_hash"] else ["metrics"]
            delta.append(comment)
        else:
            comment["delta_status"] = "unchanged"
            comment["changed_fields"] = []
    return delta
