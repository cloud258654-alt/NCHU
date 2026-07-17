from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ml.safe_text_features import summarize_text_features


BASELINE_VERSION = "rules-baseline-2026-07-18"
MODEL_KIND = "deterministic_rules_baseline"

POSITIVE_TERMS = frozenset(
    {
        "clean",
        "friendly",
        "good",
        "great",
        "helpful",
        "kind",
        "love",
        "nice",
        "polite",
        "professional",
        "quick",
        "recommend",
        "satisfied",
    }
)
NEGATIVE_TERMS = frozenset(
    {
        "angry",
        "bad",
        "broken",
        "dirty",
        "disappointed",
        "expensive",
        "late",
        "poor",
        "refund",
        "rude",
        "sick",
        "slow",
        "terrible",
        "unhappy",
        "unsafe",
        "wait",
        "worse",
        "worst",
    }
)
RISK_TERMS = frozenset(
    {
        "allergy",
        "chargeback",
        "danger",
        "fraud",
        "illegal",
        "injury",
        "lawsuit",
        "refund",
        "scam",
        "sick",
        "threat",
        "unsafe",
    }
)
SERVICE_TERMS = frozenset({"rude", "friendly", "helpful", "polite", "professional", "slow", "wait"})
PRICE_TERMS = frozenset({"cheap", "expensive", "overpriced", "price", "refund"})
QUALITY_TERMS = frozenset({"broken", "clean", "dirty", "fresh", "good", "poor", "quality", "terrible"})


@dataclass(frozen=True)
class ReviewAnalysisInput:
    content: str
    review_id: str | None = None
    business_id: str | None = None
    platform: str | None = None
    title: str | None = None
    language: str | None = None


def analyze_review(payload: ReviewAnalysisInput) -> dict[str, Any]:
    text = " ".join(part for part in (payload.title, payload.content) if part).strip()
    tokens = _tokens(text)
    positive_hits = _hits(tokens, POSITIVE_TERMS)
    negative_hits = _hits(tokens, NEGATIVE_TERMS)
    risk_hits = _hits(tokens, RISK_TERMS)

    sentiment_score = _clamp((len(positive_hits) - len(negative_hits)) / 5)
    risk_score = _clamp(len(risk_hits) / 3 + max(len(negative_hits) - len(positive_hits), 0) / 8)
    categories = _categories(tokens)
    features = summarize_text_features(text)

    return {
        "review_id": payload.review_id,
        "business_id": payload.business_id,
        "platform": payload.platform,
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "sentiment": _sentiment(sentiment_score),
        "sentiment_score": round(sentiment_score, 3),
        "risk_level": _risk_level(risk_score),
        "risk_score": round(risk_score, 3),
        "confidence": _confidence(features.word_count, positive_hits, negative_hits, risk_hits),
        "categories": categories,
        "matched_terms": {
            "positive": sorted(positive_hits),
            "negative": sorted(negative_hits),
            "risk": sorted(risk_hits),
        },
        "summary": _summary(text, sentiment_score, risk_score),
        "suggested_actions": _suggested_actions(sentiment_score, risk_score, categories),
        "features": asdict(features),
        "limitations": [
            "This is a deterministic rules baseline, not a recovered original model.",
            "This is not a production-grade trained machine learning model.",
            "No trained-model accuracy is claimed.",
        ],
    }


def analyze_batch(items: list[ReviewAnalysisInput]) -> dict[str, Any]:
    analyses = [analyze_review(item) for item in items]
    risk_counts: dict[str, int] = {}
    sentiment_counts: dict[str, int] = {}
    for item in analyses:
        risk_counts[item["risk_level"]] = risk_counts.get(item["risk_level"], 0) + 1
        sentiment_counts[item["sentiment"]] = sentiment_counts.get(item["sentiment"], 0) + 1
    return {
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "count": len(analyses),
        "items": analyses,
        "aggregate": {
            "risk_counts": risk_counts,
            "sentiment_counts": sentiment_counts,
        },
    }


def suggest_response(
    *,
    review_text: str,
    business_name: str | None = None,
    sentiment: str | None = None,
    risk_level: str | None = None,
    tone: str | None = None,
) -> dict[str, Any]:
    inferred = analyze_review(ReviewAnalysisInput(content=review_text))
    final_sentiment = (sentiment or inferred["sentiment"]).lower()
    final_risk = (risk_level or inferred["risk_level"]).lower()
    final_tone = (tone or "professional").lower()
    name = business_name or "our team"

    if final_risk == "high":
        response = (
            f"Thank you for telling {name} about this issue. We take this seriously and would like "
            "to review the details directly. Please contact our team with your visit information so we can follow up."
        )
    elif final_sentiment == "positive":
        response = (
            f"Thank you for the feedback. {name} appreciates your support and will keep working to provide a good experience."
        )
    elif final_sentiment == "negative":
        response = (
            f"Thank you for sharing this. {name} is sorry the experience did not meet expectations. "
            "We will review the issue and use it to improve our service."
        )
    else:
        response = (
            f"Thank you for your review. {name} values the feedback and will continue improving the customer experience."
        )

    return {
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "tone": final_tone,
        "suggested_response": response,
        "rationale": {
            "sentiment": final_sentiment,
            "risk_level": final_risk,
            "method": "deterministic template selected from rules baseline",
        },
        "limitations": [
            "This response is generated by deterministic templates, not by an LLM.",
            "Human review is required before customer-facing use.",
        ],
    }


def model_info() -> dict[str, Any]:
    return {
        "service": "dashboard-ml-offline-analysis",
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "original_model_restored": False,
        "production_grade_ml": False,
        "uses_pickle_or_joblib": False,
        "uses_ollama_or_llm": False,
        "description": "Offline deterministic rules baseline for versioned analysis API development.",
        "endpoints": [
            "GET /api/ml/health",
            "GET /api/ml/info",
            "POST /api/ml/analyze-review",
            "POST /api/ml/analyze-batch",
            "POST /api/ai/suggest-response",
        ],
        "limitations": [
            "Not the original recovered model.",
            "Not a production-grade trained machine learning model.",
            "No trained-model accuracy is claimed.",
            "Ollama and LLM integrations are deferred.",
        ],
    }


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z'-]*", text.lower()))


def _hits(tokens: set[str], terms: frozenset[str]) -> set[str]:
    return tokens.intersection(terms)


def _clamp(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _sentiment(score: float) -> str:
    if score >= 0.2:
        return "positive"
    if score <= -0.2:
        return "negative"
    return "neutral"


def _risk_level(score: float) -> str:
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"


def _categories(tokens: set[str]) -> list[str]:
    categories = []
    if tokens.intersection(SERVICE_TERMS):
        categories.append("service")
    if tokens.intersection(PRICE_TERMS):
        categories.append("price")
    if tokens.intersection(QUALITY_TERMS):
        categories.append("quality")
    if tokens.intersection(RISK_TERMS):
        categories.append("risk")
    return categories or ["general"]


def _confidence(word_count: int, positive_hits: set[str], negative_hits: set[str], risk_hits: set[str]) -> str:
    signal_count = len(positive_hits) + len(negative_hits) + len(risk_hits)
    if word_count >= 8 and signal_count >= 2:
        return "medium"
    if signal_count >= 1:
        return "low"
    return "low"


def _summary(text: str, sentiment_score: float, risk_score: float) -> str:
    if not text.strip():
        return "No review text was provided."
    sentiment = _sentiment(sentiment_score)
    risk = _risk_level(risk_score)
    return f"Rules baseline classified the review as {sentiment} sentiment with {risk} risk."


def _suggested_actions(sentiment_score: float, risk_score: float, categories: list[str]) -> list[str]:
    actions = []
    if risk_score >= 0.66:
        actions.append("Escalate for manual review before responding.")
    elif risk_score >= 0.33:
        actions.append("Review the issue and prepare a factual follow-up.")
    if sentiment_score <= -0.2:
        actions.append("Acknowledge the complaint and identify an owner for follow-up.")
    if "service" in categories:
        actions.append("Check service workflow notes for the reported touchpoint.")
    return actions or ["Monitor the review and respond according to standard service guidelines."]
