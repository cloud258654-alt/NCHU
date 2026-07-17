from datetime import datetime, timezone

from api.enriched_reputation import aggregate_enriched_rows


def test_row_level_enriched_reviews_are_aggregated() -> None:
    rows = [
        {
            "platform": "google_maps",
            "sentiment": "positive",
            "risk_score": 20,
            "risk_level": "low",
            "summary": "整體評價穩定。",
            "updated_at": datetime(2026, 7, 11, 1, 0, tzinfo=timezone.utc),
        },
        {
            "platform": "google_maps",
            "sentiment": "負面",
            "risk_score": 80,
            "risk_level": "高",
            "updated_at": datetime(2026, 7, 11, 2, 0, tzinfo=timezone.utc),
        },
    ]

    platform_rows, summary, numeric = aggregate_enriched_rows(rows, set(rows[0]))

    assert platform_rows[0]["total"] == 2
    assert platform_rows[0]["positive"] == 1
    assert platform_rows[0]["negative"] == 1
    assert platform_rows[0]["risk_score"] == 50
    assert platform_rows[0]["risk_rank"] == 3
    assert summary == "整體評價穩定。"
    assert numeric is True


def test_pre_aggregated_enriched_rows_are_supported() -> None:
    rows = [
        {
            "source_platform": "ptt",
            "total_reviews": 10,
            "positive_count": 4,
            "neutral_count": 3,
            "negative_count": 2,
            "unclassified_count": 1,
            "average_risk_score": 60,
            "risk_grade": "medium",
        }
    ]

    platform_rows, _, _ = aggregate_enriched_rows(rows, set(rows[0]))

    assert platform_rows[0]["total"] == 10
    assert platform_rows[0]["analyzed"] == 9
    assert platform_rows[0]["unclassified"] == 1
    assert platform_rows[0]["risk_score"] == 60
