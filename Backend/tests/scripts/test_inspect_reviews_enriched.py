from scripts.inspect_reviews_enriched import (
    evaluate_contract,
    report_exit_code,
    safe_sample_columns,
)


ACTUAL_REVIEWS_ENRICHED_COLUMNS = {
    "review_id",
    "reviewer",
    "review_time",
    "raw_text",
    "rating",
    "platform",
    "sentiment_label",
    "sentiment_score",
    "risk_score",
    "risk_level",
    "flag_food_safety",
    "flag_legal_risk",
    "flag_hygiene_risk",
    "emotion_joy",
    "emotion_anger",
    "emotion_disappointment",
    "reviews_tag",
    "analyzed_at",
}


def test_contract_accepts_shared_view_without_business_columns() -> None:
    report = evaluate_contract(ACTUAL_REVIEWS_ENRICHED_COLUMNS)

    assert report["valid"] is True
    assert report["report_scope"] == "all_rows"
    assert report["missing_required_columns"] == []
    assert report["business_filter_columns"] == []
    assert report["optional_columns_present"] == [
        "analyzed_at",
        "emotion_anger",
        "emotion_disappointment",
        "emotion_joy",
        "flag_food_safety",
        "flag_hygiene_risk",
        "flag_legal_risk",
        "rating",
        "review_time",
        "reviews_tag",
        "risk_level",
        "risk_score",
        "sentiment_score",
    ]


def test_contract_rejects_missing_sentiment_label() -> None:
    report = evaluate_contract(
        ACTUAL_REVIEWS_ENRICHED_COLUMNS.difference({"sentiment_label"})
    )

    assert report["valid"] is False
    assert report["missing_required_columns"] == ["sentiment_label"]


def test_safe_sample_columns_excludes_reviewer_and_raw_text() -> None:
    selected = safe_sample_columns(ACTUAL_REVIEWS_ENRICHED_COLUMNS)

    assert selected == [
        "review_id",
        "platform",
        "sentiment_label",
        "sentiment_score",
        "rating",
        "risk_score",
        "risk_level",
        "flag_food_safety",
        "flag_legal_risk",
        "flag_hygiene_risk",
        "analyzed_at",
        "review_time",
    ]
    assert "reviewer" not in selected
    assert "raw_text" not in selected


def test_report_exit_code_requires_existing_valid_contract() -> None:
    assert report_exit_code(
        {"exists": False, "contract": {"valid": True}}
    ) == 1
    assert report_exit_code(
        {"exists": True, "contract": {"valid": False}}
    ) == 1
    assert report_exit_code(
        {"exists": True, "contract": {"valid": True}}
    ) == 0
