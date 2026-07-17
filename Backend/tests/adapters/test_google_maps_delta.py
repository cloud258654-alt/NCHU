from datetime import datetime, timedelta, timezone
import sys

import pytest

from adapters.google_maps import crawler
from adapters.google_maps.delta import (
    classify_google_reviews,
    existing_record_from_review,
    google_review_identity,
    normalize_place_url,
)
from adapters.google_maps.crawler import _limit_reviews, _review_limit_enabled
from core.supabase import ExistingGoogleReviewIndex, PersistenceResult, PersistenceStageResult


def _index_for(review, *, place_url):
    identity, _ = google_review_identity(review, place_url=place_url)
    return ExistingGoogleReviewIndex(
        by_place={normalize_place_url(place_url): {identity: existing_record_from_review(review, place_url=place_url)}},
        available=True,
        source="test",
        records_loaded=1,
    )


def test_classify_google_reviews_skips_unchanged_payload():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    place_url = "https://www.google.com/maps/place/Example?authuser=0&entry=ttu"
    review = {
        "id": "review-1",
        "author_name": "Alice",
        "content": "Good soup",
        "rating": 5,
        "published_at": (now - timedelta(days=1)).isoformat(),
        "like_count": 1,
        "reply_count": 0,
        "reaction_count": 0,
    }

    result = classify_google_reviews(
        [{"post_url": place_url, "reviews": [dict(review)]}],
        existing_index=_index_for(review, place_url=place_url),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["posts"] == []
    assert result["diagnostics"]["unchanged_reviews"] == 1
    assert result["diagnostics"]["delta_reviews"] == 0
    assert result["diagnostics"]["change_status"] == "no_changes"


def test_classify_google_reviews_distinguishes_content_and_metric_changes():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    place_url = "https://www.google.com/maps/place/Example"
    old = {
        "id": "review-1",
        "author_name": "Alice",
        "content": "Good soup",
        "rating": 5,
        "published_at": (now - timedelta(days=1)).isoformat(),
        "like_count": 1,
        "reply_count": 0,
        "reaction_count": 0,
    }
    changed_content = {**old, "content": "Great soup"}
    changed_metric = {**old, "id": "review-2", "like_count": 3}
    index = _index_for(old, place_url=place_url)
    identity, _ = google_review_identity(changed_metric, place_url=place_url)
    index.by_place[normalize_place_url(place_url)][identity] = existing_record_from_review(
        {**changed_metric, "like_count": 1},
        place_url=place_url,
    )

    result = classify_google_reviews(
        [{"post_url": place_url, "reviews": [changed_content, changed_metric]}],
        existing_index=index,
        window_start=now - timedelta(days=30),
        window_end=now,
        diff_mode="strict",
    )

    assert result["diagnostics"]["changed_reviews"] == 2
    assert result["diagnostics"]["changed_content_reviews"] == 1
    assert result["diagnostics"]["changed_metric_reviews"] == 1
    assert result["diagnostics"]["ai_items_enqueued"] == 1
    assert result["diagnostics"]["delta_reviews"] == 2


def test_classify_google_reviews_skips_reviews_older_than_window():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    place_url = "https://www.google.com/maps/place/Example"
    old_review = {
        "id": "review-31",
        "author_name": "Alice",
        "content": "Old",
        "rating": 4,
        "published_at": (now - timedelta(days=31)).isoformat(),
    }

    result = classify_google_reviews(
        [{"post_url": place_url, "reviews": [old_review]}],
        existing_index=_index_for({**old_review, "published_at": (now - timedelta(days=1)).isoformat()}, place_url=place_url),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["posts"] == []
    assert result["diagnostics"]["older_reviews_skipped"] == 1
    assert result["diagnostics"]["reviews_in_window"] == 0


def test_classify_google_reviews_baselines_new_place_without_lookback_filter():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    place_url = "https://www.google.com/maps/place/Example"
    old_review = {
        "id": "review-31",
        "author_name": "Alice",
        "content": "Old but canonical baseline",
        "rating": 4,
        "published_at": (now - timedelta(days=365)).isoformat(),
    }

    result = classify_google_reviews(
        [{"post_url": place_url, "reviews": [old_review]}],
        existing_index=ExistingGoogleReviewIndex(by_place={}, available=True, source="test", records_loaded=0),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert len(result["place_posts"]) == 1
    assert len(result["posts"]) == 1
    assert result["diagnostics"]["baseline_places"] == 1
    assert result["diagnostics"]["baseline_reviews"] == 1
    assert result["diagnostics"]["older_reviews_skipped"] == 0


def test_classify_google_reviews_baselines_each_new_place_independently():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    posts = [
        {
            "post_url": "https://www.google.com/maps/place/A",
            "reviews": [{"id": "a-1", "author_name": "Alice", "content": "A", "published_at": (now - timedelta(days=90)).isoformat()}],
        },
        {
            "post_url": "https://www.google.com/maps/place/B",
            "reviews": [{"id": "b-1", "author_name": "Bob", "content": "B", "published_at": (now - timedelta(days=120)).isoformat()}],
        },
    ]

    result = classify_google_reviews(
        posts,
        existing_index=ExistingGoogleReviewIndex(by_place={}, available=True, source="test", records_loaded=0),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["diagnostics"]["baseline_places"] == 2
    assert result["diagnostics"]["baseline_reviews"] == 2
    assert len(result["place_posts"]) == 2


def test_classify_google_reviews_repeated_run_dedupes_unchanged_review():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    place_url = "https://www.google.com/maps/place/Example"
    review = {
        "id": "review-1",
        "author_name": "Alice",
        "content": "Same",
        "rating": 5,
        "published_at": (now - timedelta(days=1)).isoformat(),
    }

    result = classify_google_reviews(
        [{"post_url": place_url, "reviews": [dict(review)]}],
        existing_index=_index_for(review, place_url=place_url),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["posts"] == []
    assert result["place_posts"][0]["reviews"] == []
    assert result["diagnostics"]["unchanged_reviews"] == 1
    assert result["diagnostics"]["ai_items_enqueued"] == 0


def test_limit_reviews_applies_positive_cap_only():
    posts = [
        {"reviews": [{"id": "1"}, {"id": "2"}]},
        {"reviews": [{"id": "3"}]},
    ]

    _limit_reviews(posts, max_reviews=2)

    assert [review["id"] for review in posts[0]["reviews"]] == ["1", "2"]
    assert posts[1]["reviews"] == []


def test_google_maps_max_results_caps_baseline_reviews_before_classification():
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    posts = [{"post_url": "https://www.google.com/maps/place/Example", "reviews": [{"id": str(i)} for i in range(5)]}]
    _limit_reviews(posts, max_reviews=3)

    result = classify_google_reviews(
        posts,
        existing_index=ExistingGoogleReviewIndex(by_place={}, available=True, source="test", records_loaded=0),
        window_start=now - timedelta(days=30),
        window_end=now,
    )

    assert result["diagnostics"]["baseline_reviews"] == 3


def test_zero_google_maps_max_reviews_means_no_review_cap():
    assert not _review_limit_enabled(None)
    assert not _review_limit_enabled(0)
    assert _review_limit_enabled(1)


@pytest.mark.asyncio
async def test_google_maps_main_reports_persistence_partial_failure(monkeypatch):
    now = datetime.now(timezone.utc)
    place_url = "https://www.google.com/maps/place/Example"

    async def fake_scrape_google_maps(*args, **kwargs):
        return [
            {
                "post_url": place_url,
                "title": "Google Maps reviews: Example",
                "content": "Example reviews",
                "source": "google_maps",
                "reviews": [
                    {
                        "id": "review-1",
                        "author_name": "Alice",
                        "content": "Good",
                        "rating": 5,
                        "published_at": now.isoformat(),
                    }
                ],
            }
        ]

    monkeypatch.setattr(crawler, "scrape_google_maps", fake_scrape_google_maps)
    monkeypatch.setattr(
        crawler.db,
        "load_existing_google_review_index",
        lambda *args, **kwargs: ExistingGoogleReviewIndex(by_place={}, available=True, source="test", records_loaded=0),
    )
    monkeypatch.setattr(
        crawler.db,
        "save_google_reviews_with_result",
        lambda posts: PersistenceResult(
            stages=[
                PersistenceStageResult("canonical_posts", True, 1, 1),
                PersistenceStageResult("canonical_comments", True, 1, 1),
                PersistenceStageResult("post_metric_snapshots", False, 1, 0, "db_write_failed", "write failed"),
            ]
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crawler.py",
            "--url",
            place_url,
            "--business-name",
            "Example",
            "--max-scroll",
            "0",
            "--max-minutes",
            "1",
        ],
    )

    result = await crawler.main()

    assert result["status"] == "partial_success"
    assert result["error_type"] == "persistence_partial_failure"
    assert result["persistence"]["canonical_posts_written"] == 1
    assert result["persistence"]["failed_stages"] == ["post_metric_snapshots"]


@pytest.mark.asyncio
async def test_google_maps_main_persists_latest_place_with_zero_delta_reviews(monkeypatch):
    now = datetime.now(timezone.utc)
    place_url = "https://www.google.com/maps/place/Example"
    review = {
        "id": "review-1",
        "author_name": "Alice",
        "content": "Same",
        "rating": 5,
        "published_at": now.isoformat(),
    }
    saved_payloads = []

    async def fake_scrape_google_maps(*args, **kwargs):
        return [
            {
                "post_url": place_url,
                "title": "Google Maps reviews: Example",
                "content": "Example reviews",
                "source": "google_maps",
                "reviews": [dict(review)],
            }
        ]

    def fake_save(posts):
        saved_payloads.extend(posts)
        return PersistenceResult(
            stages=[
                PersistenceStageResult("canonical_posts", True, 1, 1),
            ]
        )

    monkeypatch.setattr(crawler, "scrape_google_maps", fake_scrape_google_maps)
    monkeypatch.setattr(
        crawler.db,
        "load_existing_google_review_index",
        lambda *args, **kwargs: _index_for(review, place_url=place_url),
    )
    monkeypatch.setattr(crawler.db, "save_google_reviews_with_result", fake_save)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "crawler.py",
            "--url",
            place_url,
            "--business-name",
            "Example",
            "--max-scroll",
            "0",
            "--max-minutes",
            "1",
        ],
    )

    result = await crawler.main()

    assert saved_payloads and saved_payloads[0]["reviews"] == []
    assert result["canonical_posts_written"] == 1
    assert result["canonical_comments_written"] == 0
