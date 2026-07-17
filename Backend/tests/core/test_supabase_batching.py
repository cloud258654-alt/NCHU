from __future__ import annotations

import sys
from pathlib import Path
import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import core.supabase as supabase


def test_save_crawled_post_records_batches_related_rows(monkeypatch):
    monkeypatch.setenv("BI_RMP_DB_POST_BATCH_SIZE", "2")
    monkeypatch.setenv("BI_RMP_DB_METRIC_BATCH_SIZE", "2")
    monkeypatch.setenv("BI_RMP_DB_COMMENT_BATCH_SIZE", "2")

    post_upsert_sizes: list[int] = []
    metric_upsert_sizes: list[int] = []
    comment_upsert_sizes: list[int] = []
    comment_metric_insert_sizes: list[int] = []

    monkeypatch.setattr(supabase, "_crawled_post_row", lambda post: {"link": post["source_url"]})
    monkeypatch.setattr(supabase, "_dedupe_crawled_post_rows", lambda rows: list(rows))

    def fake_upsert_posts(rows):
        post_upsert_sizes.append(len(rows))
        return {row["link"]: f"post-{idx}" for idx, row in enumerate(rows)}

    def fake_upsert_comments(rows):
        comment_upsert_sizes.append(len(rows))
        return {row["dedupe_key"]: f"comment-{idx}" for idx, row in enumerate(rows)}

    monkeypatch.setattr(supabase, "_upsert_crawled_post_rows", fake_upsert_posts)
    monkeypatch.setattr(supabase, "_insert_post_metrics", lambda rows: metric_upsert_sizes.append(len(rows)))
    monkeypatch.setattr(supabase, "_upsert_comments", fake_upsert_comments)
    monkeypatch.setattr(supabase, "_insert_comment_metrics", lambda rows: comment_metric_insert_sizes.append(len(rows)))
    monkeypatch.setattr(supabase, "extract_post_metrics", lambda payload, captured_at: [{"like_count": 1}])
    monkeypatch.setattr(supabase, "extract_comment_metrics", lambda comment, collected_at: {"like_count": 1})

    def fake_extract_comments(raw_payload, *, platform, post_source_url):
        return raw_payload.get("comments", [])

    monkeypatch.setattr(supabase, "extract_comments", fake_extract_comments)

    posts = [
        {
            "source_url": f"https://example.com/post-{idx}",
            "platform": "threads",
            "raw_json": {
                "comments": [
                    {
                        "dedupe_key": f"comment-{idx}",
                        "content": f"comment {idx}",
                        "crawl_job_id": "job-1",
                    }
                ]
            },
        }
        for idx in range(5)
    ]

    saved = supabase.save_crawled_post_records(posts)

    assert saved == 5
    assert post_upsert_sizes == [2, 2, 1]
    assert metric_upsert_sizes == [2, 2, 1]
    assert comment_upsert_sizes == [2, 2, 1]
    assert comment_metric_insert_sizes == [2, 2, 1]


def test_save_platform_posts_streams_normalized_records(monkeypatch):
    seen: dict[str, object] = {}

    def fake_save_crawled_post_records(records):
        seen["is_list"] = isinstance(records, list)
        materialized = list(records)
        seen["count"] = len(materialized)
        return len(materialized)

    monkeypatch.setattr(supabase, "save_crawled_post_records", fake_save_crawled_post_records)
    monkeypatch.setattr(
        supabase,
        "standardize_crawled_post",
        lambda post, **kwargs: {"source_url": post["post_url"], "platform": kwargs["platform"]},
    )

    saved = supabase._save_platform_posts(
        [
            {"post_url": "https://example.com/a"},
            {"post_url": "https://example.com/b"},
        ],
        platform="threads",
    )

    assert saved == 2
    assert seen == {"is_list": False, "count": 2}


def test_only_canonical_posts_persist_latest_crawl_job_id():
    post_source = inspect.getsource(supabase._upsert_crawled_post_rows_postgres)
    comment_source = inspect.getsource(supabase._upsert_comments)
    post_metric_source = inspect.getsource(supabase._insert_post_metrics)
    comment_metric_source = inspect.getsource(supabase._insert_comment_metrics)

    assert "crawl_job_id, platform_post_id" in post_source
    assert "crawl_job_id = EXCLUDED.crawl_job_id" in post_source
    assert "crawl_job_id" not in comment_source
    assert "crawl_job_id" not in post_metric_source
    assert "crawl_job_id" not in comment_metric_source


def test_comment_conflict_update_moves_comment_to_current_post():
    source = inspect.getsource(supabase._upsert_comments)

    assert "ON CONFLICT (dedupe_key) DO UPDATE SET" in source
    assert "crawl_post_id = EXCLUDED.crawl_post_id" in source


def test_reputation_pipeline_fields_are_in_persistence_sql():
    post_source = inspect.getsource(supabase._upsert_crawled_post_rows_postgres)
    metric_source = inspect.getsource(supabase._insert_post_metrics)
    comment_source = inspect.getsource(supabase._upsert_comments)
    comment_metric_source = inspect.getsource(supabase._insert_comment_metrics)

    assert "average_rating" not in post_source
    assert "rating_count" not in post_source
    assert "average_rating, rating_count, extra_data" in metric_source
    assert "rating_value" not in comment_source
    assert "rating_value" in comment_metric_source


def test_comment_row_keeps_rating_value_out_of_canonical_columns():
    row = supabase._comment_row(
        {
            "crawl_post_id": "post-1",
            "dedupe_key": "comment-1",
            "content": "好吃",
            "rating_value": "4.5",
        }
    )

    assert "rating_value" not in row
    assert row["extra_data"]["rating_value"] == "4.5"
