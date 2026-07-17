from api.quantitative_report import attach_quantitative_metrics


def test_quantitative_metrics_use_analyzed_reviews_as_sentiment_denominator() -> None:
    summary = {
        "overview": {
            "total_reviews": 10,
            "analyzed_reviews": 8,
            "positive": 4,
            "neutral": 1,
            "negative": 3,
            "unclassified": 2,
        },
        "platforms": [
            {
                "platform": "google_maps",
                "total": 5,
                "analyzed": 4,
                "positive": 3,
                "neutral": 0,
                "negative": 1,
                "unclassified": 1,
            }
        ],
    }

    result = attach_quantitative_metrics(summary)

    assert result["overview"]["analysis_coverage_pct"] == 80.0
    assert result["overview"]["positive_pct"] == 50.0
    assert result["overview"]["neutral_pct"] == 12.5
    assert result["overview"]["negative_pct"] == 37.5
    assert result["overview"]["unclassified_pct"] == 20.0
    assert result["overview"]["dominant_sentiment"] == "positive"
    assert result["overview"]["platform_count"] == 1
    assert result["platforms"][0]["negative_pct"] == 25.0
    assert result["report_contract"]["report_type"] == "reviews_enriched_quantitative"


def test_quantitative_metrics_handle_empty_report() -> None:
    summary = {
        "overview": {
            "total_reviews": 0,
            "analyzed_reviews": 0,
            "positive": 0,
            "neutral": 0,
            "negative": 0,
            "unclassified": 0,
        },
        "platforms": [],
    }

    result = attach_quantitative_metrics(summary)

    assert result["overview"]["analysis_coverage_pct"] == 0.0
    assert result["overview"]["negative_pct"] == 0.0
    assert result["overview"]["dominant_sentiment"] == "unclassified"
    assert result["overview"]["platform_count"] == 0
