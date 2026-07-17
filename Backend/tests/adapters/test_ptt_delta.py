from datetime import datetime, timedelta, timezone

from adapters.ptt.delta import ExistingPttIndex, classify_ptt_posts, existing_ptt_record_from_row, normalize_ptt_url


def _post(now, **overrides):
    post = {
        "external_id": "M.1.html",
        "post_url": "https://www.ptt.cc/bbs/Food/M.1.html",
        "source_url": "https://www.ptt.cc/bbs/Food/M.1.html",
        "title": "Good soup",
        "content": "Good beef soup",
        "author_id": "alice",
        "author_name": "alice",
        "post_time": (now - timedelta(days=1)).isoformat(),
        "push_count": 1,
        "boo_count": 0,
        "arrow_count": 0,
        "comment_count": 1,
        "reaction_count": 1,
        "comments": [
            {
                "author_id": "bob",
                "author_name": "bob",
                "content": "nice",
                "comment_type": "push",
                "comment_time_raw": "07/10 10:00",
                "like_count": 0,
            }
        ],
    }
    post.update(overrides)
    return post


def _index_for(post):
    record = existing_ptt_record_from_row(
        {
            "platform_post_id": post["external_id"],
            "link": post["post_url"],
            "title": post["title"],
            "content": post["content"],
            "author_id": post["author_id"],
            "author_name": post["author_name"],
            "published_at": post["post_time"],
            "comment_count": post["comment_count"],
            "reaction_count": post["reaction_count"],
            "extra_data": {"ptt_metrics": {"push_count": post["push_count"], "boo_count": 0, "arrow_count": 0}},
        },
        post["comments"],
    )
    return ExistingPttIndex(
        by_external_id={post["external_id"]: record},
        by_normalized_url={normalize_ptt_url(post["post_url"]): record},
        available=True,
        source="test",
        records_loaded=1,
    )


def test_classify_ptt_posts_skips_unchanged_payload():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    post = _post(now)

    result = classify_ptt_posts(
        [dict(post)],
        existing_index=_index_for(post),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["posts"] == []
    assert result["diagnostics"]["unchanged_items"] == 1
    assert result["diagnostics"]["delta_items"] == 0


def test_classify_ptt_posts_detects_new_and_skips_unknown_time():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    unknown_time = _post(now, external_id="M.unknown.html", post_time=None)

    result = classify_ptt_posts(
        [_post(now), unknown_time],
        existing_index=ExistingPttIndex({}, {}, True, "test", 0),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert len(result["posts"]) == 1
    assert result["diagnostics"]["new_items"] == 1
    assert result["diagnostics"]["unknown_time_skipped"] == 1
    assert result["diagnostics"]["ai_items_enqueued"] == 1


def test_classify_ptt_posts_skips_older_than_window():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    old = _post(now, post_time=(now - timedelta(days=31)).isoformat())

    result = classify_ptt_posts(
        [old],
        existing_index=ExistingPttIndex({}, {}, True, "test", 0),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["posts"] == []
    assert result["diagnostics"]["older_items_skipped"] == 1
