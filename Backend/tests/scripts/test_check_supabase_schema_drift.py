from scripts.check_supabase_schema_drift import (
    diff_schema_objects,
    expected_objects,
    is_protected_table,
    load_allowlist,
)


def test_schema_allowlist_contains_core_schema_objects():
    allowlist = load_allowlist()
    expected = expected_objects(allowlist)

    assert {
        "alerts",
        "analysis_results",
        "business",
        "client_messages_log",
        "clients",
        "comment_metric_snapshots",
        "crawl_comments",
        "crawl_jobs",
        "crawl_logs",
        "crawl_posts",
        "post_metric_snapshots",
        "reputation_score_snapshots",
        "service_tasks",
    }.issubset(expected["table"])
    assert expected["view"] == {"reviews_enriched"}
    assert is_protected_table("reviews_enriched", allowlist)
    assert is_protected_table("review_google_maps", allowlist)
    assert is_protected_table("master_reviews_enriched", allowlist)


def test_diff_schema_objects_reports_extra_and_missing_objects():
    allowlist = {
        "tables": ["business", "clients"],
        "views": ["business_table_editor"],
        "protected_tables": ["master_reviews_enriched"],
        "protected_table_patterns": ["review%"],
    }

    diff = diff_schema_objects(
        [
            ("business", "table"),
            ("old_review", "table"),
            ("review_google_maps", "table"),
            ("master_reviews_enriched", "table"),
            ("extra_view", "view"),
            ("sequence_like", "sequence"),
        ],
        allowlist,
    )

    assert diff == {
        "extra_tables": ["old_review"],
        "missing_tables": ["clients"],
        "extra_views": ["extra_view"],
        "missing_views": ["business_table_editor"],
        "unexpected_object_types": ["sequence_like:sequence"],
    }
