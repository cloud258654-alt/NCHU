from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from backend.app import app  # noqa: E402
from ml.rules_baseline import (  # noqa: E402
    ANALYSIS_METHOD,
    ANALYSIS_TYPE,
    BASELINE_VERSION,
    CONTRACT_VERSION,
    MODEL_KIND,
    MODEL_NAME,
    ReviewAnalysisInput,
    analyze_review,
)


def _client() -> TestClient:
    return TestClient(app)


def test_ml_health_reports_offline_rules_baseline() -> None:
    response = _client().get("/api/ml/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "dashboard-ml-offline-analysis",
        "model_kind": MODEL_KIND,
        "trained_model_available": False,
    }


def test_ml_info_disclaims_original_model_and_production_accuracy() -> None:
    response = _client().get("/api/ml/info")
    payload = response.json()

    assert response.status_code == 200
    assert payload["model_name"] == "bi-rmp-rules-baseline"
    assert payload["model_version"] == BASELINE_VERSION
    assert payload["analysis_method"] == "rules_baseline"
    assert payload["analysis_type"] == ANALYSIS_TYPE
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["original_model_restored"] is False
    assert payload["production_grade_ml"] is False
    assert payload["uses_pickle_or_joblib"] is False
    assert payload["uses_ollama_or_llm"] is False
    assert payload["supported_languages"] == ["en", "zh-TW"]
    assert payload["risk_score_scale"] == {
        "min": 0,
        "max": 100,
        "low_lt": 33,
        "medium_lt": 66,
        "critical_gte": 90,
    }
    assert payload["risk_level_values"] == ["low", "medium", "high"]
    assert payload["escalation_level_values"] == ["none", "review", "urgent", "critical"]
    assert payload["response_contract"]["response_suggestion_keys"] == ["en", "zh_tw"]
    assert payload["response_contract"]["analysis_id_format"] == "rules-v{model_version_dash}-{sha256_32}"
    assert "No trained-model accuracy is claimed." in payload["limitations"]


def test_analyze_review_returns_contract_and_deterministic_sentiment() -> None:
    response = _client().post(
        "/api/ml/analyze-review",
        json={
            "review_id": "r-101",
            "business_id": "b-7",
            "platform": "google_maps",
            "title": "Great service",
            "content": "The staff were friendly and helpful. I recommend this place.",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["review_id"] == "r-101"
    assert payload["sentiment_label"] == "positive"
    assert payload["sentiment"] == "positive"
    assert payload["risk_level"] == "low"
    assert 0 <= payload["risk_score"] <= 100
    assert payload["model_name"] == MODEL_NAME
    assert payload["model_version"] == BASELINE_VERSION
    assert payload["analysis_method"] == ANALYSIS_METHOD
    assert payload["analysis_type"] == ANALYSIS_TYPE
    assert re.fullmatch(r"rules-v1-2-0-[0-9a-f]{32}", payload["analysis_id"])
    assert payload["analyzed_at"].endswith("Z")
    assert payload["human_review_required"] is False
    assert payload["critical"] is False
    assert payload["critical_signals"] == []
    assert payload["escalation_level"] == "none"
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["response_contract"]["version"] == CONTRACT_VERSION
    assert set(payload["response_suggestion"]) == {"en", "zh_tw"}
    assert payload["trained_model_available"] is False
    assert payload["model_kind"] == MODEL_KIND
    assert payload["baseline_version"] == BASELINE_VERSION
    assert "service" in payload["categories"]
    assert payload["features"]["word_count"] >= 8


def test_analyze_review_flags_risk_terms_on_100_point_scale() -> None:
    response = _client().post(
        "/api/ml/analyze-review",
        json={
            "content": "The food made me sick and the place felt unsafe. I want a refund.",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["sentiment_label"] == "negative"
    assert payload["sentiment"] == "negative"
    assert payload["risk_score"] >= 33
    assert payload["risk_level"] in {"medium", "high"}
    assert payload["escalation_level"] in {"review", "urgent", "critical"}
    assert payload["human_review_required"] is True
    assert "risk" in payload["categories"]
    assert "Escalate for manual review before responding." in payload["suggested_actions"]


def test_analyze_review_supports_traditional_chinese_positive_service() -> None:
    response = _client().post(
        "/api/ml/analyze-review",
        json={
            "review_id": "zh-1",
            "business_id": "b-zh",
            "platform": "threads",
            "language": "zh-TW",
            "content": "\u670d\u52d9\u5f88\u89aa\u5207\uff0c\u74b0\u5883\u4e7e\u6de8\uff0c\u9910\u9ede\u597d\u5403\uff0c\u6211\u6703\u63a8\u85a6\u670b\u53cb\u518d\u4f86\u3002",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["sentiment_label"] == "positive"
    assert payload["risk_score"] == 0
    assert payload["risk_level"] == "low"
    assert "service" in payload["topics"]
    assert "quality" in payload["topics"]
    assert {"\u89aa\u5207", "\u4e7e\u6de8", "\u597d\u5403", "\u63a8\u85a6"}.issubset(set(payload["tags"]))
    assert "\u611f\u8b1d" in payload["response_suggestion"]["zh_tw"]
    assert "Thank" in payload["response_suggestion"]["en"]


def test_analyze_review_supports_traditional_chinese_risk() -> None:
    response = _client().post(
        "/api/ml/analyze-review",
        json={
            "review_id": "zh-risk",
            "language": "zh-TW",
            "content": "\u7b49\u592a\u4e45\u800c\u4e14\u614b\u5ea6\u5dee\uff0c\u9910\u9ede\u4e0d\u65b0\u9bae\uff0c\u5403\u5b8c\u7591\u4f3c\u98df\u7269\u4e2d\u6bd2\uff0c\u8981\u6c42\u9000\u8cbb\u3002",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["sentiment_label"] == "negative"
    assert payload["risk_score"] >= 66
    assert payload["risk_level"] == "high"
    assert payload["human_review_required"] is True
    assert payload["critical"] is True
    assert payload["escalation_level"] == "critical"
    assert "\u98df\u7269\u4e2d\u6bd2" in payload["critical_signals"]
    assert "risk" in payload["topics"]
    assert "\u98df\u7269\u4e2d\u6bd2" in payload["tags"]
    assert "\u4eba\u5de5\u5be9\u67e5" in payload["response_suggestion"]["zh_tw"]


def test_analyze_review_flags_critical_signals_without_expanding_risk_level_enum() -> None:
    response = _client().post(
        "/api/ml/analyze-review",
        json={
            "review_id": "critical-1",
            "business_id": "b-critical",
            "platform": "google_maps",
            "content": "This unsafe incident caused an injury and we may contact police and media.",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["risk_score"] >= 90
    assert payload["risk_level"] == "high"
    assert payload["critical"] is True
    assert payload["critical_signals"] == ["injury", "media", "police", "unsafe"]
    assert payload["escalation_level"] == "critical"
    assert payload["human_review_required"] is True
    assert set(payload["response_suggestion"]) == {"en", "zh_tw"}


def test_analyze_batch_returns_items_and_aggregate() -> None:
    response = _client().post(
        "/api/ml/analyze-batch",
        json={
            "items": [
                {"review_id": "1", "content": "Great and friendly service."},
                {"review_id": "2", "content": "Slow service and a bad wait."},
            ]
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["count"] == 2
    assert len(payload["items"]) == 2
    assert payload["aggregate"]["sentiment_counts"]["positive"] == 1
    assert payload["aggregate"]["sentiment_counts"]["negative"] == 1
    assert payload["model_name"] == MODEL_NAME
    assert payload["model_version"] == BASELINE_VERSION
    assert payload["analysis_method"] == ANALYSIS_METHOD
    assert payload["analysis_type"] == ANALYSIS_TYPE
    assert payload["contract_version"] == CONTRACT_VERSION
    assert all("sentiment_label" in item for item in payload["items"])
    assert all(item["response_contract"]["version"] == CONTRACT_VERSION for item in payload["items"])


def test_analyze_batch_rejects_empty_batch() -> None:
    response = _client().post("/api/ml/analyze-batch", json={"items": []})

    assert response.status_code == 422


def test_suggest_response_uses_deterministic_bilingual_template_not_llm() -> None:
    response = _client().post(
        "/api/ai/suggest-response",
        json={
            "business_name": "Demo Shop",
            "review_text": "The service was slow and I am unhappy.",
            "sentiment": "negative",
            "risk_level": "medium",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["model_name"] == MODEL_NAME
    assert payload["model_version"] == BASELINE_VERSION
    assert payload["analysis_method"] == ANALYSIS_METHOD
    assert payload["analysis_type"] == ANALYSIS_TYPE
    assert re.fullmatch(r"rules-v1-2-0-[0-9a-f]{32}", payload["analysis_id"])
    assert re.fullmatch(r"response-[0-9a-f]{24}", payload["response_id"])
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["trained_model_available"] is False
    assert payload["response_contract"]["response_suggestion_keys"] == ["en", "zh_tw"]
    assert payload["response_suggestion"] == payload["suggested_response"]
    assert payload["human_review_required"] is True
    assert payload["rationale"]["risk_level"] == "medium"
    assert payload["rationale"]["escalation_level"] == "review"
    assert payload["rationale"]["method"] == "deterministic template selected from rules baseline"
    assert "Demo Shop" in payload["suggested_response"]["en"]
    assert "\u62b1\u6b49" in payload["suggested_response"]["zh_tw"]
    assert "LLM" in payload["limitations"][0]


def test_rules_baseline_is_deterministic_except_analyzed_at() -> None:
    payload = ReviewAnalysisInput(content="Great service but the wait was slow.")

    first = analyze_review(payload)
    second = analyze_review(payload)

    assert first["analysis_id"] == second["analysis_id"]
    assert first["sentiment_label"] == second["sentiment_label"]
    assert first["risk_level"] == second["risk_level"]
    assert first["risk_score"] == second["risk_score"]
    assert first["topics"] == second["topics"]


def test_analysis_id_uses_canonical_whitespace_and_versioned_format() -> None:
    first = analyze_review(
        ReviewAnalysisInput(
            review_id="stable-1",
            business_id="b-1",
            platform="ptt",
            language="en",
            title="Slow service",
            content="The   wait\nwas\ttoo long.",
        )
    )
    second = analyze_review(
        ReviewAnalysisInput(
            review_id="stable-1",
            business_id="b-1",
            platform="ptt",
            language="en",
            title="Slow service",
            content="The wait was too long.",
        )
    )
    different_review = analyze_review(
        ReviewAnalysisInput(
            review_id="stable-2",
            business_id="b-1",
            platform="ptt",
            language="en",
            title="Slow service",
            content="The wait was too long.",
        )
    )

    assert first["analysis_id"] == second["analysis_id"]
    assert first["analysis_id"] != different_review["analysis_id"]
    assert re.fullmatch(r"rules-v1-2-0-[0-9a-f]{32}", first["analysis_id"])


def test_analyze_review_contract_contains_required_fields() -> None:
    response = _client().post(
        "/api/ml/analyze-review",
        json={"review_id": "contract-1", "content": "\u666e\u901a\u7684\u4e00\u6b21\u6d88\u8cbb\u9ad4\u9a57\u3002"},
    )
    payload = response.json()
    required = {
        "review_id",
        "business_id",
        "platform",
        "sentiment_label",
        "sentiment_score",
        "risk_score",
        "risk_level",
        "topics",
        "tags",
        "response_suggestion",
        "model_name",
        "model_version",
        "analysis_method",
        "analysis_type",
        "analysis_id",
        "analyzed_at",
        "human_review_required",
        "critical",
        "critical_signals",
        "escalation_level",
        "contract_version",
        "response_contract",
        "limitations",
    }

    assert response.status_code == 200
    assert required.issubset(payload)
    assert payload["model_name"] == "bi-rmp-rules-baseline"
    assert payload["model_version"] == BASELINE_VERSION
    assert payload["analysis_method"] == "rules_baseline"
    assert payload["analysis_type"] == ANALYSIS_TYPE
    assert payload["contract_version"] == CONTRACT_VERSION


def test_suggest_response_accepts_mvp_escalation_terms() -> None:
    response = _client().post(
        "/api/ai/suggest-response",
        json={
            "business_name": "Demo Shop",
            "review_text": "Customer reported a serious safety issue.",
            "sentiment": "negative",
            "risk_level": "urgent",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["rationale"]["risk_level"] == "high"
    assert payload["rationale"]["escalation_level"] == "urgent"
    assert set(payload["suggested_response"]) == {"en", "zh_tw"}


def test_no_fake_model_artifacts_are_created() -> None:
    model_files = list((APP_ROOT / "models").glob("*"))
    blocked_suffixes = {".pkl", ".pickle", ".joblib"}

    assert all(path.suffix.lower() not in blocked_suffixes for path in model_files)
