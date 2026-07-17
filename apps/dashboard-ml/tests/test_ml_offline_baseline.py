from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from backend.app import app  # noqa: E402
from ml.rules_baseline import (  # noqa: E402
    ANALYSIS_METHOD,
    BASELINE_VERSION,
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
    assert payload["original_model_restored"] is False
    assert payload["production_grade_ml"] is False
    assert payload["uses_pickle_or_joblib"] is False
    assert payload["uses_ollama_or_llm"] is False
    assert payload["supported_languages"] == ["en", "zh-TW"]
    assert "No trained-model accuracy is claimed." in payload["limitations"]


def test_analyze_review_returns_deterministic_sentiment_and_risk() -> None:
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
    assert payload["model_name"] == MODEL_NAME
    assert payload["model_version"] == BASELINE_VERSION
    assert payload["analysis_method"] == ANALYSIS_METHOD
    assert payload["analysis_id"].startswith("rules-")
    assert payload["analyzed_at"].endswith("Z")
    assert payload["human_review_required"] is False
    assert payload["response_suggestion"]
    assert payload["trained_model_available"] is False
    assert payload["model_kind"] == MODEL_KIND
    assert payload["baseline_version"] == BASELINE_VERSION
    assert "service" in payload["categories"]
    assert payload["features"]["word_count"] >= 8


def test_analyze_review_flags_risk_terms() -> None:
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
    assert payload["risk_level"] in {"medium", "high"}
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
            "content": "服務很親切，環境乾淨，餐點好吃，我會推薦朋友再來。",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["sentiment_label"] == "positive"
    assert payload["risk_level"] == "low"
    assert "service" in payload["topics"]
    assert "quality" in payload["topics"]
    assert {"親切", "乾淨", "好吃", "推薦"}.issubset(set(payload["tags"]))
    assert payload["response_suggestion"].startswith("建議")


def test_analyze_review_supports_traditional_chinese_risk() -> None:
    response = _client().post(
        "/api/ml/analyze-review",
        json={
            "review_id": "zh-risk",
            "language": "zh-TW",
            "content": "等太久而且態度差，餐點不新鮮，吃完疑似食物中毒，要求退費。",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["sentiment_label"] == "negative"
    assert payload["risk_level"] == "high"
    assert payload["human_review_required"] is True
    assert "risk" in payload["topics"]
    assert "食物中毒" in payload["tags"]
    assert "人工審查" in payload["response_suggestion"]


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
    assert all("sentiment_label" in item for item in payload["items"])


def test_analyze_batch_rejects_empty_batch() -> None:
    response = _client().post("/api/ml/analyze-batch", json={"items": []})

    assert response.status_code == 422


def test_suggest_response_uses_deterministic_template_not_llm() -> None:
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
    assert payload["trained_model_available"] is False
    assert payload["rationale"]["method"] == "deterministic template selected from rules baseline"
    assert "Demo Shop" in payload["suggested_response"]
    assert "LLM" in payload["limitations"][0]


def test_rules_baseline_is_deterministic() -> None:
    payload = ReviewAnalysisInput(content="Great service but the wait was slow.")

    first = analyze_review(payload)
    second = analyze_review(payload)

    assert first["analysis_id"] == second["analysis_id"]
    assert first["sentiment_label"] == second["sentiment_label"]
    assert first["risk_level"] == second["risk_level"]
    assert first["topics"] == second["topics"]


def test_analyze_review_contract_contains_required_fields() -> None:
    response = _client().post(
        "/api/ml/analyze-review",
        json={"review_id": "contract-1", "content": "普通的一次消費體驗。"},
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
        "analysis_id",
        "analyzed_at",
        "human_review_required",
        "limitations",
    }

    assert response.status_code == 200
    assert required.issubset(payload)


def test_no_fake_model_artifacts_are_created() -> None:
    model_files = list((APP_ROOT / "models").glob("*"))
    blocked_suffixes = {".pkl", ".pickle", ".joblib"}

    assert all(path.suffix.lower() not in blocked_suffixes for path in model_files)
