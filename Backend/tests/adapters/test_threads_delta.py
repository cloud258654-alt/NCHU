from datetime import datetime, timedelta, timezone

from adapters.threads.delta import (
    ExistingThreadsIndex,
    classify_threads_posts,
    existing_threads_record_from_row,
    normalize_threads_url,
)


def _post(now, **overrides):
    post = {
        "external_id": "abc123",
        "post_url": "https://www.threads.net/@alice/post/abc123/",
        "source_url": "https://www.threads.net/@alice/post/abc123/",
        "content": "Good beef soup",
        "author_id": "alice",
        "author_name": "Alice",
        "post_time": (now - timedelta(days=1)).isoformat(),
        "like_count": 1,
        "comment_count": 1,
        "share_count": 0,
        "reaction_count": 1,
        "comments": [
            {
                "external_id": "reply-1",
                "source_url": "https://www.threads.net/@bob/post/reply-1/",
                "author_id": "bob",
                "author_name": "Bob",
                "content": "nice",
                "like_count": 0,
                "reply_count": 0,
                "reaction_count": 0,
            }
        ],
    }
    post.update(overrides)
    return post


def _index_for(post):
    record = existing_threads_record_from_row(
        {
            "platform_post_id": post["external_id"],
            "link": post["post_url"],
            "content": post["content"],
            "author_id": post["author_id"],
            "author_name": post["author_name"],
            "published_at": post["post_time"],
            "like_count": post["like_count"],
            "comment_count": post["comment_count"],
            "share_count": post["share_count"],
            "reaction_count": post["reaction_count"],
        },
        post["comments"],
    )
    return ExistingThreadsIndex(
        by_post_id={post["external_id"]: record},
        by_normalized_url={normalize_threads_url(post["post_url"]): record},
        available=True,
        source="test",
        records_loaded=1,
    )


def test_classify_threads_posts_skips_unchanged_payload():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    post = _post(now)

    result = classify_threads_posts(
        [dict(post)],
        existing_index=_index_for(post),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["posts"] == []
    assert result["diagnostics"]["unchanged_items"] == 1
    assert result["diagnostics"]["delta_items"] == 0


def test_classify_threads_posts_detects_metric_change_without_ai_enqueue():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    old = _post(now)
    changed = _post(now, like_count=5, reaction_count=5)

    result = classify_threads_posts(
        [changed],
        existing_index=_index_for(old),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert len(result["posts"]) == 1
    assert result["diagnostics"]["changed_metric_items"] == 1
    assert result["diagnostics"]["ai_items_enqueued"] == 0


def test_classify_threads_posts_skips_unknown_time_and_old_items():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    unknown = _post(now, external_id="unknown", post_time=None)
    old = _post(now, external_id="old", post_time=(now - timedelta(days=31)).isoformat())

    result = classify_threads_posts(
        [unknown, old],
        existing_index=ExistingThreadsIndex({}, {}, True, "test", 0),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["posts"] == []
    assert result["diagnostics"]["unknown_time_skipped"] == 1
    assert result["diagnostics"]["older_items_skipped"] == 1
