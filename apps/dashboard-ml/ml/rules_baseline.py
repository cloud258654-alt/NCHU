from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from ml.safe_text_features import summarize_text_features


MODEL_NAME = "bi-rmp-rules-baseline"
BASELINE_VERSION = "1.1.0"
MODEL_KIND = "deterministic_rules_baseline"
ANALYSIS_METHOD = "rules_baseline"

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

ZH_POSITIVE_TERMS = frozenset(
    {
        "\u4e7e\u6de8",
        "\u53cb\u5584",
        "\u597d\u5403",
        "\u5c08\u696d",
        "\u63a8\u85a6",
        "\u6eff\u610f",
        "\u89aa\u5207",
        "\u8b9a",
        "\u5feb\u901f",
        "\u559c\u6b61",
        "\u8212\u670d",
        "\u7d30\u5fc3",
    }
)
ZH_NEGATIVE_TERMS = frozenset(
    {
        "\u4e0d\u6eff",
        "\u5931\u671b",
        "\u751f\u6c23",
        "\u5f88\u6162",
        "\u96e3\u5403",
        "\u9ad2",
        "\u614b\u5ea6\u5dee",
        "\u7cdf\u7cd5",
        "\u9000\u8cbb",
        "\u7b49\u592a\u4e45",
        "\u8cb4",
        "\u4e0d\u6703\u518d\u4f86",
        "\u4e0d\u63a8\u85a6",
    }
)
ZH_RISK_TERMS = frozenset(
    {
        "\u98df\u7269\u4e2d\u6bd2",
        "\u904e\u654f",
        "\u53d7\u50b7",
        "\u5371\u96aa",
        "\u8a50\u9a19",
        "\u9055\u6cd5",
        "\u63d0\u544a",
        "\u5ba2\u8a34",
        "\u9000\u8cbb",
        "\u4e0d\u5b89\u5168",
    }
)
ZH_SERVICE_TERMS = frozenset(
    {
        "\u670d\u52d9",
        "\u89aa\u5207",
        "\u614b\u5ea6",
        "\u614b\u5ea6\u5dee",
        "\u7b49\u592a\u4e45",
        "\u5f88\u6162",
        "\u5c08\u696d",
        "\u7d30\u5fc3",
    }
)
ZH_PRICE_TERMS = frozenset(
    {
        "\u50f9\u683c",
        "\u8cb4",
        "\u592a\u8cb4",
        "\u9000\u8cbb",
        "\u6536\u8cbb",
    }
)
ZH_QUALITY_TERMS = frozenset(
    {
        "\u54c1\u8cea",
        "\u597d\u5403",
        "\u96e3\u5403",
        "\u4e7e\u6de8",
        "\u9ad2",
        "\u65b0\u9bae",
        "\u7cdf\u7cd5",
    }
)


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
    positive_hits = _hits(tokens, POSITIVE_TERMS) | _phrase_hits(text, ZH_POSITIVE_TERMS)
    negative_hits = _hits(tokens, NEGATIVE_TERMS) | _phrase_hits(text, ZH_NEGATIVE_TERMS)
    risk_hits = _hits(tokens, RISK_TERMS) | _phrase_hits(text, ZH_RISK_TERMS)

    sentiment_score = _clamp_ratio((len(positive_hits) - len(negative_hits)) / 5)
    risk_ratio = _clamp_ratio(len(risk_hits) / 3 + max(len(negative_hits) - len(positive_hits), 0) / 8)
    risk_score = round(risk_ratio * 100, 1)
    topics = _topics(tokens, text)
    features = summarize_text_features(text)
    sentiment_label = _sentiment(sentiment_score)
    risk_level = _risk_level(risk_score)
    response_suggestion = _analysis_response_suggestion(
        sentiment_label=sentiment_label,
        risk_level=risk_level,
    )
    human_review_required = risk_level == "high" or bool(risk_hits)
    limitations = [
        "This is a deterministic rules baseline, not a recovered original model.",
        "This is not a production-grade trained machine learning model.",
        "No trained-model accuracy is claimed.",
        "Traditional Chinese support is rules-based phrase matching, not a trained language model.",
    ]

    return {
        "review_id": payload.review_id,
        "business_id": payload.business_id,
        "platform": payload.platform,
        "sentiment_label": sentiment_label,
        "sentiment_score": round(sentiment_score, 3),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "topics": topics,
        "tags": sorted(positive_hits | negative_hits | risk_hits),
        "response_suggestion": response_suggestion,
        "model_name": MODEL_NAME,
        "model_version": BASELINE_VERSION,
        "analysis_method": ANALYSIS_METHOD,
        "analysis_id": _analysis_id(payload, text),
        "analyzed_at": _analyzed_at(),
        "human_review_required": human_review_required,
        "limitations": limitations,
        # Backward-compatible fields retained for Gate 4 clients.
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "sentiment": sentiment_label,
        "confidence": _confidence(features.word_count, positive_hits, negative_hits, risk_hits),
        "categories": topics,
        "matched_terms": {
            "positive": sorted(positive_hits),
            "negative": sorted(negative_hits),
            "risk": sorted(risk_hits),
        },
        "summary": _summary(sentiment_score, risk_score),
        "suggested_actions": _suggested_actions(sentiment_score, risk_score, topics),
        "features": asdict(features),
    }


def analyze_batch(items: list[ReviewAnalysisInput]) -> dict[str, Any]:
    analyses = [analyze_review(item) for item in items]
    risk_counts: dict[str, int] = {}
    sentiment_counts: dict[str, int] = {}
    for item in analyses:
        risk_counts[item["risk_level"]] = risk_counts.get(item["risk_level"], 0) + 1
        sentiment_counts[item["sentiment_label"]] = sentiment_counts.get(item["sentiment_label"], 0) + 1
    return {
        "model_name": MODEL_NAME,
        "model_version": BASELINE_VERSION,
        "analysis_method": ANALYSIS_METHOD,
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
    final_sentiment = (sentiment or inferred["sentiment_label"]).lower()
    final_risk = (risk_level or inferred["risk_level"]).lower()
    final_tone = (tone or "professional").lower()
    response = _suggest_response_templates(
        business_name=business_name or "our team",
        sentiment_label=final_sentiment,
        risk_level=final_risk,
    )

    return {
        "model_name": MODEL_NAME,
        "model_version": BASELINE_VERSION,
        "analysis_method": ANALYSIS_METHOD,
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
        "model_name": MODEL_NAME,
        "model_version": BASELINE_VERSION,
        "analysis_method": ANALYSIS_METHOD,
        "model_kind": MODEL_KIND,
        "baseline_version": BASELINE_VERSION,
        "trained_model_available": False,
        "original_model_restored": False,
        "production_grade_ml": False,
        "uses_pickle_or_joblib": False,
        "uses_ollama_or_llm": False,
        "description": "Offline deterministic rules baseline for versioned analysis API development.",
        "supported_languages": ["en", "zh-TW"],
        "risk_score_scale": {"min": 0, "max": 100, "low_lt": 33, "medium_lt": 66},
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


def _phrase_hits(text: str, terms: frozenset[str]) -> set[str]:
    return {term for term in terms if term in text}


def _clamp_ratio(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _sentiment(score: float) -> str:
    if score >= 0.2:
        return "positive"
    if score <= -0.2:
        return "negative"
    return "neutral"


def _risk_level(score: float) -> str:
    if score >= 66:
        return "high"
    if score >= 33:
        return "medium"
    return "low"


def _topics(tokens: set[str], text: str) -> list[str]:
    topics = []
    if tokens.intersection(SERVICE_TERMS) or _phrase_hits(text, ZH_SERVICE_TERMS):
        topics.append("service")
    if tokens.intersection(PRICE_TERMS) or _phrase_hits(text, ZH_PRICE_TERMS):
        topics.append("price")
    if tokens.intersection(QUALITY_TERMS) or _phrase_hits(text, ZH_QUALITY_TERMS):
        topics.append("quality")
    if tokens.intersection(RISK_TERMS) or _phrase_hits(text, ZH_RISK_TERMS):
        topics.append("risk")
    return topics or ["general"]


def _confidence(word_count: int, positive_hits: set[str], negative_hits: set[str], risk_hits: set[str]) -> str:
    signal_count = len(positive_hits) + len(negative_hits) + len(risk_hits)
    if word_count >= 8 and signal_count >= 2:
        return "medium"
    if signal_count >= 1:
        return "low"
    return "low"


def _summary(sentiment_score: float, risk_score: float) -> str:
    sentiment = _sentiment(sentiment_score)
    risk = _risk_level(risk_score)
    return f"Rules baseline classified the review as {sentiment} sentiment with {risk} risk."


def _analysis_response_suggestion(*, sentiment_label: str, risk_level: str) -> dict[str, str]:
    return _suggest_response_templates(
        business_name="the business",
        sentiment_label=sentiment_label,
        risk_level=risk_level,
    )


def _suggest_response_templates(*, business_name: str, sentiment_label: str, risk_level: str) -> dict[str, str]:
    if risk_level == "high":
        return {
            "en": (
                f"Thank you for telling {business_name} about this issue. We take this seriously and would like "
                "to review the details directly. Please contact our team with your visit information so we can follow up."
            ),
            "zh_tw": (
                "\u611f\u8b1d\u60a8\u544a\u77e5\u9019\u500b\u554f\u984c\u3002"
                "\u6211\u5011\u6703\u512a\u5148\u4eba\u5de5\u5be9\u67e5\u4e26\u78ba\u8a8d\u4e8b\u5be6\uff0c"
                "\u8acb\u63d0\u4f9b\u6d88\u8cbb\u8cc7\u8a0a\u4ee5\u4fbf\u5f8c\u7e8c\u8655\u7406\u3002"
            ),
        }
    if sentiment_label == "negative":
        return {
            "en": (
                f"Thank you for sharing this. {business_name} is sorry the experience did not meet expectations. "
                "We will review the issue and use it to improve our service."
            ),
            "zh_tw": (
                "\u611f\u8b1d\u60a8\u7684\u56de\u994b\u3002"
                "\u5f88\u62b1\u6b49\u9019\u6b21\u9ad4\u9a57\u672a\u9054\u9810\u671f\uff0c"
                "\u6211\u5011\u6703\u6aa2\u8996\u554f\u984c\u4e26\u6301\u7e8c\u6539\u5584\u670d\u52d9\u3002"
            ),
        }
    if sentiment_label == "positive":
        return {
            "en": (
                f"Thank you for the feedback. {business_name} appreciates your support and will keep working "
                "to provide a good experience."
            ),
            "zh_tw": (
                "\u611f\u8b1d\u60a8\u7684\u652f\u6301\u8207\u80af\u5b9a\uff0c"
                "\u6211\u5011\u6703\u6301\u7e8c\u7dad\u6301\u670d\u52d9\u54c1\u8cea\u3002"
            ),
        }
    return {
        "en": f"Thank you for your review. {business_name} values the feedback and will continue improving.",
        "zh_tw": "\u611f\u8b1d\u60a8\u7684\u56de\u994b\uff0c\u6211\u5011\u6703\u6301\u7e8c\u6539\u5584\u9867\u5ba2\u9ad4\u9a57\u3002",
    }


def _analysis_id(payload: ReviewAnalysisInput, text: str) -> str:
    raw = "|".join(
        [
            BASELINE_VERSION,
            payload.review_id or "",
            payload.business_id or "",
            payload.platform or "",
            payload.language or "",
            text,
        ]
    )
    return "rules-" + sha256(raw.encode("utf-8")).hexdigest()[:24]


def _analyzed_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _suggested_actions(sentiment_score: float, risk_score: float, categories: list[str]) -> list[str]:
    actions = []
    if risk_score >= 66:
        actions.append("Escalate for manual review before responding.")
    elif risk_score >= 33:
        actions.append("Review the issue and prepare a factual follow-up.")
    if sentiment_score <= -0.2:
        actions.append("Acknowledge the complaint and identify an owner for follow-up.")
    if "service" in categories:
        actions.append("Check service workflow notes for the reported touchpoint.")
    return actions or ["Monitor the review and respond according to standard service guidelines."]
