from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from backend.app import app  # noqa: E402
from ml.rules_baseline import BASELINE_VERSION, MODEL_KIND, analyze_review, ReviewAnalysisInput  # noqa: E402


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
    assert payload["sentiment"] == "positive"
    assert payload["risk_level"] == "low"
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
    assert payload["sentiment"] == "negative"
    assert payload["risk_level"] in {"medium", "high"}
    assert "risk" in payload["categories"]
    assert "Escalate for manual review before responding." in payload["suggested_actions"]


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

    assert first == second


def test_no_fake_model_artifacts_are_created() -> None:
    model_files = list((APP_ROOT / "models").glob("*"))
    blocked_suffixes = {".pkl", ".pickle", ".joblib"}

    assert all(path.suffix.lower() not in blocked_suffixes for path in model_files)
