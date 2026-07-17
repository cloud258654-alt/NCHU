from __future__ import annotations

import pytest

from api.reputation import DatabaseConfigurationError
from api.reviews_enriched import (
    ReviewsEnrichedRepository,
    _build_reviews_enriched_quantitative_sql,
    _configured_reviews_enriched_relation,
    _validate_reviews_enriched_columns,
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


def test_all_line_users_resolve_to_same_global_report_scope() -> None:
    repository = ReviewsEnrichedRepository(connection_factory=lambda: None)

    first = repository.resolve_business(
        line_user_id="U-known",
        business_name="文章牛肉湯",
        business_id=7,
    )
    second = repository.resolve_business(
        line_user_id="U-unknown",
        business_name=None,
        business_id=None,
    )

    assert first == second
    assert first.id == 0
    assert first.name == "全體評論"


def test_report_relation_defaults_to_shared_reviews_enriched(monkeypatch) -> None:
    monkeypatch.delenv("BI_RMP_ENRICHED_REVIEW_TABLE", raising=False)

    assert _configured_reviews_enriched_relation() == (
        "public",
        "reviews_enriched",
    )


@pytest.mark.parametrize(
    "relation",
    [
        "public.bi_rmp_reviews_enriched",
        "public.master_reviews_enriched",
        "public.some_other_view",
    ],
)
def test_unapproved_relations_are_rejected(
    monkeypatch,
    relation: str,
) -> None:
    monkeypatch.setenv("BI_RMP_ENRICHED_REVIEW_TABLE", relation)

    with pytest.raises(DatabaseConfigurationError):
        _configured_reviews_enriched_relation()


def test_invalid_schema_identifier_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv(
        "BI_RMP_ENRICHED_REVIEW_TABLE",
        "public;drop schema public.reviews_enriched",
    )

    with pytest.raises(DatabaseConfigurationError):
        _configured_reviews_enriched_relation()


def test_actual_supabase_contract_is_accepted() -> None:
    _validate_reviews_enriched_columns(ACTUAL_REVIEWS_ENRICHED_COLUMNS)


def test_contract_does_not_require_business_fields() -> None:
    _validate_reviews_enriched_columns(
        ACTUAL_REVIEWS_ENRICHED_COLUMNS.difference(
            {"business_id", "business_name"}
        )
    )


def test_contract_requires_sentiment_label() -> None:
    with pytest.raises(DatabaseConfigurationError, match="sentiment_label"):
        _validate_reviews_enriched_columns(
            ACTUAL_REVIEWS_ENRICHED_COLUMNS.difference({"sentiment_label"})
        )


def test_quantitative_sql_aggregates_every_row_without_business_filter() -> None:
    query = _build_reviews_enriched_quantitative_sql(
        schema_name="public",
        table_name="reviews_enriched",
        columns=ACTUAL_REVIEWS_ENRICHED_COLUMNS,
    )

    assert 'FROM "public"."reviews_enriched"' in query
    assert 'btrim("sentiment_label"::text)' in query
    assert '"analyzed_at"::timestamptz AS updated_at' in query
    assert "FROM all_reviews" in query
    assert '"business_id" = %s' not in query
    assert "BUSINESS_ID" not in query.upper()
    assert "SELECT * FROM" not in query.upper()


def test_missing_optional_risk_score_is_safe() -> None:
    query = _build_reviews_enriched_quantitative_sql(
        schema_name="public",
        table_name="reviews_enriched",
        columns=ACTUAL_REVIEWS_ENRICHED_COLUMNS.difference({"risk_score"}),
    )

    assert "NULL::numeric AS risk_score" in query
