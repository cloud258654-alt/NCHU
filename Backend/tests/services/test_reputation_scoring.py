from services.nlp_analysis import analyze_text
from services.reputation_scoring import (
    google_native_score,
    impact_weight,
    load_reputation_scoring_config,
    ptt_comment_native_score,
    ptt_post_native_score,
    score_to_rating,
    threads_raw_engagement,
)


def test_reputation_scoring_config_loads_version_and_weights():
    config = load_reputation_scoring_config()

    assert config["version"] == "urs_v1"
    assert config["analysis"]["mode"] == "none"
    assert config["google_maps"]["native_weight"] == 0.70
    assert config["threads"]["engagement"]["repost"] == 2.0


def test_native_scores_do_not_require_nlp():
    assert google_native_score(1) == 0
    assert google_native_score(3) == 50
    assert google_native_score(5) == 100
    assert ptt_post_native_score(1, 1, 1) == 50
    assert ptt_comment_native_score("push") == (75.0, "native_type_only", 0.35)
    assert score_to_rating(75) == 4.0


def test_threads_engagement_changes_impact_not_sentiment_direction():
    raw = threads_raw_engagement(
        like_count=10,
        reply_count=2,
        repost_count=3,
        quote_count=1,
        view_count=100,
    )

    assert raw == 26.0
    assert impact_weight(90) == 1.85


def test_nlp_none_mode_returns_pending_null_scores():
    result = analyze_text("這家店很好吃", mode="none")

    assert result["analysis_status"] == "pending"
    assert result["sentiment"] is None
    assert result["sentiment_score_normalized"] is None
    assert result["analysis_method"] == "none"
