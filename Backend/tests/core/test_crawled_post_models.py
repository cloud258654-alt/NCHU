from core.crawled_post_models import (
    extract_comment_metrics,
    extract_comments,
    extract_post_metrics,
    standardize_crawled_post,
    standardize_search_result,
)
from core.supabase import _dedupe_crawled_post_rows


def test_standardize_crawled_post_maps_common_fields():
    item = {
        "url": "https://www.threads.net/@brand/post/abc/",
        "title": "Threads post",
        "author": "Long Author Name",
        "description": "Description",
        "like_count": 3,
        "comment_count": 4,
        "upload_date": "2026-07-01",
    }

    post = standardize_crawled_post(
        item,
        platform="threads",
        keyword="牛肉湯",
        crawl_job_id="job-1",
        parsed_time=None,
    )

    assert post == {
        "crawl_job_id": "job-1",
        "platform": "threads",
        "keyword": "牛肉湯",
        "source_url": "https://www.threads.net/@brand/post/abc/",
        "external_id": None,
        "title": "Threads post",
        "author_name": "Long Author Name",
        "author_id": None,
        "content": "Description",
        "post_time_raw": "2026-07-01",
        "posted_at": None,
        "raw_json": item,
    }

    metrics = extract_post_metrics(item)

    assert metrics == [{"collected_at": None, "comment_count": 4, "like_count": 3}]


def test_standardize_search_result_maps_to_crawled_post_shape():
    result = {
        "engine": "bing",
        "keyword": "牛肉湯",
        "query": "牛肉湯",
        "rank": 1,
        "url": "https://www.ptt.cc/bbs/Food/M.1.A.ABC.html",
        "title": "PTT result",
        "snippet": "A public post snippet",
        "detected_platform": "ptt",
        "raw_json": {"source": "fixture"},
        "crawl_job_id": "job-1",
    }

    post = standardize_search_result(result, keyword="牛肉湯")

    assert post["crawl_job_id"] == "job-1"
    assert post["platform"] == "ptt"
    assert post["keyword"] == "牛肉湯"
    assert post["source_url"] == "https://www.ptt.cc/bbs/Food/M.1.A.ABC.html"
    assert post["title"] == "PTT result"
    assert post["content"] == "A public post snippet"
    assert post["raw_json"]["search_result"] == result


def test_ptt_payload_extracts_comments_and_post_metrics():
    item = {
        "source_url": "https://www.ptt.cc/bbs/Food/M.1.A.ABC.html",
        "title": "PTT post",
        "comment_count": 3,
        "reaction_count": 3,
        "comments": [
            {
                "author_id": "bob",
                "author_name": "bob",
                "content": "好吃",
                "comment_type": "push",
                "comment_time_raw": "07/04 13:00",
                "raw_json": {"push_tag": "推"},
            }
        ],
    }

    metrics = extract_post_metrics(item)
    comments = extract_comments(item, platform="ptt", post_source_url=item["source_url"])

    assert metrics == [{"collected_at": None, "comment_count": 3, "reaction_count": 3}]
    assert len(comments) == 1
    assert comments[0]["comment_type"] == "push"
    assert comments[0]["raw_json"]["push_tag"] == "推"


def test_google_metrics_preserve_official_summary_and_comment_rating():
    item = {
        "post_url": "https://maps.example/place",
        "place_url": "https://maps.example/place",
        "average_rating": 4.6,
        "rating_count": 1234,
        "comment_count": 20,
        "reviews": [
            {
                "author_name": "Alice",
                "content": "好吃",
                "rating": 5,
                "id": "review-1",
            }
        ],
    }

    metrics = extract_post_metrics(item)
    comments = extract_comments(item, platform="google_maps", post_source_url=item["post_url"])
    comment_metric = extract_comment_metrics(comments[0])

    assert metrics == [
        {
            "collected_at": None,
            "average_rating": 4.6,
            "comment_count": 20,
            "rating_count": 1234,
            "extra_data": {
                "google_maps_summary": {
                    "place_url": "https://maps.example/place",
                    "average_rating": 4.6,
                    "rating_count": 1234,
                }
            },
        }
    ]
    assert comments[0]["rating_value"] == 5
    assert comment_metric == {"collected_at": None, "like_count": 0, "rating_value": 5.0}


def test_threads_metrics_are_preserved_in_snapshot_extra_data():
    item = {
        "post_url": "https://www.threads.net/@brand/post/abc/",
        "like_count": 10,
        "comment_count": 2,
        "share_count": 1,
        "threads_metrics": {
            "like_count": 10,
            "reply_count": 2,
            "repost_count": 1,
            "quote_count": 0,
            "view_count": 0,
        },
    }

    metrics = extract_post_metrics(item)

    assert metrics[0]["extra_data"]["threads_metrics"]["repost_count"] == 1


def test_dedupe_crawled_post_rows_keeps_latest_non_null_state_per_link():
    rows = [
        {
            "link": "https://maps.example/place",
            "crawl_job_id": "job-1",
            "platform_post_id": None,
            "title": "First review",
            "author_id": None,
            "author_name": None,
            "content": "first",
            "published_at": None,
            "extra_data": {"raw_json": {"review": 1}},
        },
        {
            "link": "https://maps.example/place",
            "crawl_job_id": "job-2",
            "platform_post_id": "review-2",
            "title": "Second review",
            "author_id": None,
            "author_name": "Alice",
            "content": "second",
            "published_at": None,
            "extra_data": {"raw_json": {"review": 2}},
        },
    ]

    deduped = _dedupe_crawled_post_rows(rows)

    assert len(deduped) == 1
    assert deduped[0]["link"] == "https://maps.example/place"
    assert deduped[0]["crawl_job_id"] == "job-2"
    assert deduped[0]["platform_post_id"] == "review-2"
    assert deduped[0]["title"] == "Second review"
    assert deduped[0]["author_name"] == "Alice"
    assert deduped[0]["content"] == "second"
    assert deduped[0]["extra_data"] == {"raw_json": {"review": 2}}
